Hello! A quick tutorial:
Run "docker compose up --build --detach" in a terminal when in the Directory this Project is.
Then wait About a Minute
Then run "python test.py"
Then wait until execution is finished
Then run "python verify.py"
When composing down, run "docker compose down -v --rmi all"