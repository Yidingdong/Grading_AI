
# Grading AI System


## Running the Application

1.  **Build and Start Services:**
    From the project root directory:
    ```bash
    docker compose up --build -d
    ```
    *(This builds images and starts all services in the background.)*

2.  **Access Frontend:**
    Open [http://localhost:8080](http://localhost:8080) in your browser.
    *(Initial startup may take a few minutes.)*

## Running Integration Tests

Ensure the application is running.

1.  **Navigate to Tests Directory:**
    ```bash
    cd tests
    ```

2.  **Execute Main Test Script:**
    *(Registers users, creates courses, processes PDF, tests grading, and cleans up.)*
    ```bash
    python test.py
    ```

3.  **Execute Verification Script:**
    *(Checks service health and confirms test data cleanup.)*
    ```bash
    python verify.py
    ```

## Stopping and Cleaning Up

From the project root directory:

```bash
docker compose down -v
```
*(Stops containers and removes volumes, deleting all data.)*

To also remove built images:
```bash
docker compose down -v --rmi all
```