# queuectl: A CLI-Based Background Job Queue System

`queuectl` is a minimal, production-grade background job queue system built in Python. It is implemented as a CLI tool for enqueuing, managing, and executing shell commands in background worker processes.

This system supports persistent job storage via SQLite, automatic retries with exponential backoff, a Dead Letter Queue (DLQ) for failed jobs, and concurrent processing with multiple workers.

Demo Video
https://drive.google.com/file/d/16IHHUwJMCyg6AbVNRTPzB9f4vLsF2qa6/view?usp=drive_link

## Features

* **CLI Interface:** A clean, easy-to-use command-line interface built with `click`.
* **Persistent Storage:** Uses SQLite to ensure job data is not lost across restarts.
* **Multi-worker Processing:** Leverages Python's `multiprocessing` to run multiple jobs in parallel.
* **Automatic Retries:** Failed jobs are automatically retried using an exponential backoff strategy.
* **Dead Letter Queue (DLQ):** Jobs that exhaust all retries are moved to a DLQ for manual inspection and retry.
* **Dynamic Configuration:** Key parameters like retry counts and backoff rates can be managed via the CLI.

## Setup Instructions

Follow these steps to set up and run the project locally.

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/gupta-ashish26/queuectl_project.git
    cd queuectl_project
    ```

2.  **Create and Activate a Virtual Environment**
    ```bash
    # Create the environment
    python3 -m venv venv
    
    # Activate the environment (macOS/Linux)
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    This project's only external dependency is `click`.
    ```bash
    pip install click
    ```

4.  **Initialize the Database**
    Run the database script to create the `queue.db` file and the `jobs` table.
    ```bash
    python3 database.py
    ```

## Usage Examples

All commands are run through the `queuectl.py` script.

### 1. Enqueue a New Job
Jobs are enqueued using a JSON string. The `command` field is required.

```bash
# Enqueue a simple job with a custom ID
python3 queuectl.py enqueue "{\"id\":\"job1\",\"command\":\"echo 'Hello from job 1'\"}"

# Enqueue a job with custom retries (default is 3)
python3 queuectl.py enqueue "{\"id\":\"job2\",\"command\":\"sleep 5\", \"max_retries\": 5}"

# Enqueue a job that will fail
python3 queuectl.py enqueue "{\"id\":\"job3\",\"command\":\"ls /nonexistent_directory\"}"
```

### 2. Start Workers

Start one or more workers to process the queue.

```bash
# Start a single worker
python3 queuectl.py worker start

# Start 4 workers in parallel
python3 queuectl.py worker start --count 4
```

Press `Ctrl+C` to shut down all running workers.

### 3. Check Queue Status

Get a high-level summary of all job states.

```bash
python3 queuectl.py status
```

**Example Output:**

```
--- Job Queue Status ---
  Pending:    3
  Processing: 0
  Completed:  0
  Failed:     0
  Dead:       0
-------------------------
  Total:      3
```

### 4. List Jobs by State

Inspect jobs in a specific state (e.g., `pending`, `completed`, `dead`).

```bash
python3 queuectl.py list --state pending
```

**Example Output:**

```
--- Jobs in 'pending' state ---
ID                                   | COMMAND                   | ATTEMPTS  
----------------------------------------------------------------------
job1                                 | echo 'Hello from job 1'   | 0         
job2                                 | sleep 5                   | 0         
job3                                 | ls /nonexistent_directory | 0         
```

### 5. Manage the Dead Letter Queue (DLQ)

Inspect and retry jobs that have permanently failed.

```bash
# List all jobs in the DLQ
python3 queuectl.py dlq list

# Retry a specific failed job
python3 queuectl.py dlq retry job3
```

### 6. Configure Settings

Manage application settings like default retries.

```bash
# Set the default max retries for new jobs to 5
python3 queuectl.py config max_retries 5

# Set the exponential backoff base to 2 (delay = 2^attempts)
python3 queuectl.py config backoff_base 2
```

## Architecture Overview

The system is designed with a clear separation of concerns, broken into three main Python modules:

* `queuectl.py`: The main CLI entry point. It handles user input parsing (using `click`), manages worker processes (using `multiprocessing`), and executes job commands (using `subprocess`).
* `database.py`: A dedicated module for all database interactions. It contains all SQL queries, handles database connections, and manages the table schema.
* `config.py`: A simple helper module for reading from and writing to the `config.json` file.

For a detailed breakdown of the data model, job lifecycle, and concurrency strategy, please see the design.md file.

## Testing Instructions

To verify the core functionality, you can run the following test scenarios.

### 1. Basic Job Success

1.  **Terminal 1:** `python3 queuectl.py worker start --count 1`
2.  **Terminal 2:** `python3 queuectl.py enqueue "{\"command\":\"echo 'Test Success'\"}"`
3.  **Observe (T1):** The worker should pick up the job and log its successful completion.
4.  **Observe (T2):** `python3 queuectl.py list --state completed` should show the new job.

### 2. Retry, Backoff, and DLQ

1.  **Terminal 1:** `python3 queuectl.py worker start --count 1`
2.  **Terminal 2:** `python3 queuectl.py enqueue "{\"id\":\"fail_test\",\"command\":\"exit 1\"}"`
3.  **Observe (T1):** The worker will run the job, and it will fail. You will see it log a retry attempt with an exponential backoff delay (e.g., "in 3s"). It will repeat this for all 3 retry attempts.
4.  **Observe (T1):** After the final attempt, the worker will log that the job is being moved to the DLQ.
5.  **Observe (T2):** `python3 queuectl.py dlq list` should now show the `fail_test` job.

### 3. Multi-Worker Concurrency

1.  **Terminal 1:** (No worker running)
2.  **Terminal 2:** Enqueue 5 "sleep" jobs:
    ```bash
    python3 queuectl.py enqueue "{\"command\":\"sleep 4; echo 'job 1'\"}"
    python3 queuectl.py enqueue "{\"command\":\"sleep 4; echo 'job 2'\"}"
    python3 queuectl.py enqueue "{\"command\":\"sleep 4; echo 'job 3'\"}"
    python3 queuectl.py enqueue "{\"command\":\"sleep 4; echo 'job 4'\"}"
    python3 queuectl.py enqueue "{\"command\":\"sleep 4; echo 'job 5'\"}"
    ```
3.  **Terminal 1:** Start 3 workers: `python3 queuectl.py worker start --count 3`
4.  **Observe (T1):** You will see logs from 3 different PIDs as they *simultaneously* pick up the first 3 jobs. After 4 seconds, they will finish and immediately pick up the remaining 2 jobs.
