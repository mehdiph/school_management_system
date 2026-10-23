# Teachlog

Django school management system (PostgreSQL in production), Persian RTL UI.
Project documentation lives in `docs/`; read the relevant parts before any change.

For any feature, change or bug fix in this project, follow the `teachlog-workflow` skill.

## Always
- Never touch the production database; ask before migrating the local Docker database.
- Work on a feature branch; don't commit, push or deploy unless asked.
- Run tests with: `POSTGRES_HOST=localhost .venv/bin/python manage.py test --noinput`

## Frontend
- When changing or adding pages to an existing panel (teacher, supervisor, director, admin),
  match that panel's current design exactly; do not introduce a new visual direction.
- Use the frontend-design skill's freedom only for entirely new panels or when I ask for a redesign.