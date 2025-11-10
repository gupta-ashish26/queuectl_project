import click
import json
import uuid
import sqlite3
from database import get_db_connection, create_tables
import subprocess
import time
from datetime import datetime, timedelta, timezone
from database import (
    get_db_connection, create_tables, fetch_job_to_run, update_job_status, update_job_for_retry, retry_dlq_job
)

BACKOFF_BASE = 3

create_tables() 

@click.group()
def cli():
    pass

# --- Enqueue Command ---

@cli.command()
@click.argument('job_spec', type=str)
def enqueue(job_spec):
    try:
        data = json.loads(job_spec)
    except json.JSONDecodeError:
        click.echo("Error: Invalid JSON string.", err=True)
        return

    if 'command' not in data:
        click.echo("Error: 'command' field is required in JSON.", err=True)
        return

    job_id = data.get('id', str(uuid.uuid4()))
    command = data['command']
    max_retries = data.get('max_retries', 3)

    # --- Database Insertion ---
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO jobs (id, command, max_retries)
            VALUES (?, ?, ?)
            """,
            (job_id, command, max_retries)
        )
        
        conn.commit()
        click.echo(f"Job enqueued with ID: {job_id}")
        
    except sqlite3.IntegrityError:
        click.echo(f"Error: A job with ID '{job_id}' already exists.", err=True)
    except Exception as e:
        click.echo(f"An unexpected error occurred: {e}", err=True)
    finally:
        if conn:
            conn.close()

# --- List Command ---

@cli.command()
@click.option('--state', default='pending', help='Filter jobs by state (e.g., pending, processing, dead).')
def list(state):
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM jobs WHERE state = ?", (state,))
    jobs = cursor.fetchall()
    
    conn.close()
    
    if not jobs:
        click.echo(f"No jobs found in state: {state}")
        return

    click.echo(f"--- Jobs in '{state}' state ---")
    header = f"{'ID':<36} | {'COMMAND':<25} | {'ATTEMPTS':<10}"
    click.echo(click.style(header, bold=True))
    click.echo("-" * (36 + 3 + 25 + 3 + 10))
    
    for job in jobs:
        click.echo(f"{job['id']:<36} | {job['command']:<25} | {job['attempts']:<10}")


@cli.group()
def worker():
    pass

def _handle_job_failure(job, error_message=""):
    job_id = job['id']
    new_attempts = job['attempts'] + 1

    click.echo(click.style(f"Job {job_id} failed.", fg='red'))
    if error_message:
        click.echo(f"  Error: {error_message.strip()}")

    if new_attempts <= job['max_retries']:
        delay_seconds = BACKOFF_BASE ** new_attempts
        run_at_dt = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        run_at_sql_format = run_at_dt.strftime("%Y-%m-%d %H:%M:%S")

        click.echo(f"  Retrying job... Attempt {new_attempts} of {job['max_retries']}.")
        click.echo(f"  Next run at: {run_at_sql_format} (in {delay_seconds}s)")

        update_job_for_retry(job_id, new_attempts, run_at_sql_format)

    else:
        click.echo(click.style(f"  Job has reached max retries ({job['max_retries']}).", fg='yellow'))
        click.echo(click.style(f"  Moving job {job_id} to Dead Letter Queue.", fg='yellow'))

        update_job_status(job_id, 'dead', new_attempts)
        
def _run_job(job):
    job_id = job['id']
    command = job['command']

    click.echo(f"Running job {job_id}: {command}")

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300) # 5-min timeout

        # --- Handle Job Success ---
        if result.returncode == 0:
            click.echo(click.style(f"Job {job_id} completed successfully.", fg='green'))
            update_job_status(job_id, 'completed')

        # --- Handle Job Failure ---
        else:
            _handle_job_failure(job, result.stderr)

    except subprocess.TimeoutExpired:
        _handle_job_failure(job, "Job timed out after 300 seconds.")

    except Exception as e:
        # Catch other unexpected errors during execution
        _handle_job_failure(job, f"Unexpected error: {e}")


@worker.command()
@click.option('--count', default=1, help='Number of workers to start (we will implement this in a later phase).')
def start(count):
    
    if count > 1:
        click.echo("Note: Multi-worker is not implemented yet. Starting 1 worker.")
    
    click.echo("Starting worker... Press Ctrl+C to stop.")
    
    try:
        while True:
            job = fetch_job_to_run()
            
            if job:
                _run_job(job)
            else:
                click.echo("No pending jobs. Waiting...")
                time.sleep(5) # Wait 5 seconds
                
    except KeyboardInterrupt:
        click.echo("\nShutting down worker...")

@cli.group()
def dlq():
    pass

@dlq.command(name='list')
def dlq_list():
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM jobs WHERE state = 'dead'")
    jobs = cursor.fetchall()
    
    conn.close()
    
    if not jobs:
        click.echo("Dead Letter Queue is empty.")
        return

    click.echo(f"--- Jobs in 'dead' state ---")
    header = f"{'ID':<36} | {'COMMAND':<25} | {'ATTEMPTS':<10}"
    click.echo(click.style(header, bold=True))
    click.echo("-" * (36 + 3 + 25 + 3 + 10))
    
    for job in jobs:
        click.echo(f"{job['id']:<36} | {job['command']:<25} | {job['attempts']:<10}")

@dlq.command(name='retry')
@click.argument('job_id')
def dlq_retry(job_id):
    
    success = retry_dlq_job(job_id)
    
    if success:
        click.echo(click.style(f"Job {job_id} has been moved back to 'pending' queue.", fg='green'))
    else:
        click.echo(click.style(f"Error: Job {job_id} not found in DLQ.", fg='red'))

if __name__ == "__main__":
    cli()