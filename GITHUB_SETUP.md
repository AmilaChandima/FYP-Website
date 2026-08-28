# Upload SolarCharge to GitHub

The project is GitHub-ready. Secrets, `.venv`, `node_modules`, local optimizer runs and runtime files are excluded by `.gitignore`.

## Create a repository

Create an empty GitHub repository, for example:

```text
solarcharge-fyp
```

Do not initialize it with another README if you want the simplest first push.

## First push from VS Code terminal

From the project root:

```bash
git init
git add .
git commit -m "MongoDB shared SolarCharge system"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/solarcharge-fyp.git
git push -u origin main
```

## On another group member's laptop

```bash
git clone https://github.com/YOUR_USERNAME/solarcharge-fyp.git
cd solarcharge-fyp
```

Then create that member's private `backend/.env` using the same MongoDB connection details.

Run:

```bat
setup.bat
run.bat
```

## Normal collaboration

Before working:

```bash
git pull
```

After making code changes:

```bash
git add .
git commit -m "Describe the update"
git push
```

Do **not** send or commit `backend/.env`. Share the MongoDB connection string privately with your group members.
