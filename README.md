# Tutorial

This is a tutorial to run, test, and verify the backend of the grading app.

## Steps to Run

1. Run in a terminal when in the Directory this Project is.

```bash
docker compose up --build -d
``` 
2. do the following:
```bash
cd tests
python test.py
```
3. Then wait until execution is finished
4. Then run 
```bash
python verify.py
```
5. When composing down, run 
```bash
docker compose down -v --rmi all
```