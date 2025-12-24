Project setup
=============

## Make sure that "make" is installed

### clone the project

### cd ProjectName

### python -m venv venv

### venv\scripts\activate

### pip install poetry

### mkdir local

### cp core/project/settings/templates/settings.dev.py ./local/settings.dev.py

### (ignore if not creating new project) change environment variables prefix in core.project.settings.__init__ and in docker or .env files and entrypoint

### (ignore if not creating new project) change all project specific info "database name, pyproject.toml package name, license etc"

### make install

### make develop

### make update

### export POSTGRES_DB=fra
### export POSTGRES_USER=fra
### export POSTGRES_PASSWORD=fra
### export POSTGRES_HOST=localhost
