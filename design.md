# Design and Architecture: `queuectl`

This document details the internal design, data model, and architectural decisions for the `queuectl` job queue system.

## 1. Core Components

The application logic is separated into three primary modules:

* **`queuectl.py` (CLI & Process Manager)**
    * **Responsibilities:** Defines the entire CLI structure using the `click` library. Parses user commands and arguments.
    * Contains the `worker` logic, including the main `run_worker_loop` and the `_run_job` function which uses `subprocess.run` to execute commands.
    * Manages the pool of worker processes using Python's `multiprocessing` library.
    * Orchestrates the job lifecycle logic (e.g., calling `_handle_job_failure` on error).

* **`database.py` (Data Access Layer)**
    * **Responsibilities:** Acts as the single source of truth for all database interactions.
    * Initializes the SQLite database (`queue.db`) and creates the `jobs` table schema.
    * Provides atomic functions for fetching, locking, and updating jobs (e.g., `fetch_job_to_run`, `update_job_status`).

* **`config.py` (Configuration Manager)**
    * **Responsibilities:** Manages reading from and writing to a persistent `config.json` file.
    * Provides default values if the file or a specific key is missing.

## 2. Data Model

We use a single SQLite table named `jobs` to store all job information.

### `jobs` Table Schema

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `TEXT PRIMARY KEY` | The unique identifier for the job. |
| `command` | `TEXT NOT NULL` | The shell command to be executed. |
| `state` | `TEXT NOT NULL` | The current state of the job (`pending`, `processing`, `completed`, `failed`, `dead`). |
| `max_retries` | `INTEGER NOT NULL` | The maximum number of *retries* allowed (default is 3). |
| `attempts` | `INTEGER NOT NULL` | The number of times this job has been run. |
| `created_at`| `TEXT NOT NULL` | The ISO 8601 timestamp when the job was created. |
| `updated_at`| `TEXT NOT NULL` | The timestamp of the last state change. |
| `run_at` | `TEXT NOT NULL` | The earliest time the job can be run. This is key for the backoff mechanism. |

The `run_at` column is crucial for the retry logic. When a job fails, its `state` is set to `pending` and its `run_at` is set to a future time. Workers only fetch jobs where `run_at <= DATETIME('now')`.

## 3. Job State Lifecycle

A job moves through a defined set of states during its lifetime:

1.  **Enqueue:** A user creates a job. It enters the database in the `pending` state.
2.  **Fetch & Lock:** A worker process finds a `pending` job and atomically updates its state to `processing`.
3.  **Execution:** The worker executes the job's command.
    * **On Success:** The job's state is updated to `completed`.
    * **On Failure:** The `_handle_job_failure` logic is triggered.
4.  **Failure Handling:**
    * If `attempts < max_retries`, the state is set back to `pending`, `attempts` is incremented, and `run_at` is set to a future time based on the exponential backoff.
    * If `attempts >= max_retries`, the state is set to `dead`.
5.  **DLQ Retry:** A user can manually trigger a `dead` job using `dlq retry`. This resets its state to `pending`, `attempts` to `0`, and `run_at` to `now`.

## 4. Concurrency & Locking Strategy

The most critical challenge in a multi-worker system is preventing a "race condition" where two workers grab the *same job*.

* **Problem:** Worker A and Worker B both scan the `jobs` table at the same time. They both see `job1` is `pending`. Worker A grabs it. Worker B grabs it. The job runs twice.
* **Solution:** We use an atomic transaction with a database lock. Our `fetch_job_to_run` function in `database.py` uses the following strategy:
    1.  `BEGIN IMMEDIATE`: This SQL command acquires an **immediate exclusive lock** on the database. No other process can write *or read* from the database until this transaction is complete.
    2.  `SELECT ... LIMIT 1`: The worker securely finds the next available job.
    3.  `UPDATE ... SET state = 'processing'`: The worker "locks" the job in the database by changing its state.
    4.  `COMMIT`: The transaction is committed, releasing the lock. The worker can now safely run the job it fetched.

This strategy guarantees that even with 100 workers, a pending job can only ever be picked up by **one** worker at a time.

## 5. Assumptions and Trade-offs

* **Security (`shell=True`)**: The `subprocess.run(command, shell=True)` function is used for simplicity, as it allows users to pass complex commands like `sleep 5; echo 'done'`. In a true production system, this poses a security risk (shell injection). A safer approach would be to parse the command and arguments, running them as a list (e.g., `subprocess.run(['sleep', '5'])`).
* **Persistence (SQLite)**: SQLite is an excellent, simple, and serverless database, perfect for this assignment. Its trade-off is that it does not scale well beyond a single machine (as it relies on file-system locks). A larger system would use a dedicated client-server database (like PostgreSQL) or a message broker (like RabbitMQ or Redis).
* **Worker Shutdown (`terminate()`)**: The multi-worker `start` command uses `proc.terminate()` on `KeyboardInterrupt`. This is effective for shutting down, but it is not truly "graceful" as it kills a child process *immediately*, even if it's in the middle of a job. A more complex, fully graceful shutdown would use `signal` handling to allow a worker to finish its current job before exiting.