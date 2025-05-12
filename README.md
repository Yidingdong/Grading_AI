# Tutorial

This is a tutorial to run, test, and verify the backend of the grading app.

## Steps to Run

1. Run in a terminal when in the Directory this Project is.

```bash
docker compose up --build --d
``` 

2. Then wait About a Minute
3. do "cd tests"
4. Then run 
```bash
python test.py
```
4. Then wait until execution is finished
5. Then run 
```bash
python verify.py
```
6. When composing down, run 
```bash
docker compose down -v --rmi all
```