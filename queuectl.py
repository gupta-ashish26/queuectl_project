import click
import json
import uuid
import sqlite3
from database import get_db_connection, create_tables

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


if __name__ == "__main__":
    cli()