-- 001_initial: core schema for the ACME project-tracking system.
--
-- Conventions
--   * UUID primary keys (gen_random_uuid() is built into PostgreSQL 13+).
--   * Nothing is ever hard-deleted: every business table has archived_at.
--   * Enumerations are text + CHECK so they can evolve with plain ALTERs.
--   * updated_at is maintained by the set_updated_at() trigger.
--   * Everything is timestamptz (UTC); plain dates are calendar days.

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- users: admins, managers and employees share one table and one login.
-- salary is the person's HOURLY cost to the company (labor cost = hours * salary).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    username             varchar(6)    NOT NULL UNIQUE,
    password_hash        text          NOT NULL,
    name                 text          NOT NULL,
    email                text          NOT NULL,
    job_title            text          NOT NULL DEFAULT '',
    role                 text          NOT NULL CHECK (role IN ('admin', 'manager', 'employee')),
    manager_id           uuid          REFERENCES users (id),
    salary               numeric(10,2) NOT NULL DEFAULT 0 CHECK (salary >= 0),
    must_change_password boolean       NOT NULL DEFAULT true,
    -- Bumped on password change/reset/archive so previously issued tokens stop working.
    token_version        integer       NOT NULL DEFAULT 0,
    archived_at          timestamptz,
    created_at           timestamptz   NOT NULL DEFAULT now(),
    updated_at           timestamptz   NOT NULL DEFAULT now(),
    CHECK (manager_id IS NULL OR manager_id <> id)
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));
CREATE INDEX IF NOT EXISTS users_manager_idx ON users (manager_id);
CREATE INDEX IF NOT EXISTS users_role_idx ON users (role) WHERE archived_at IS NULL;

DROP TRIGGER IF EXISTS users_set_updated_at ON users;
CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- projects: created by an admin on behalf of exactly ONE manager.
-- Progress and risk are derived from start_date / end_date (see reports).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text          NOT NULL,
    description     text          NOT NULL DEFAULT '',
    manager_id      uuid          NOT NULL REFERENCES users (id),
    status          text          NOT NULL DEFAULT 'planned'
                                  CHECK (status IN ('planned', 'active', 'completed', 'archived')),
    start_date      date          NOT NULL,
    end_date        date          NOT NULL,
    allocated_hours numeric(10,2) NOT NULL DEFAULT 0 CHECK (allocated_hours >= 0),
    budget_amount   numeric(14,2) NOT NULL DEFAULT 0 CHECK (budget_amount >= 0),
    completed_at    timestamptz,
    archived_at     timestamptz,
    created_by      uuid          REFERENCES users (id),
    created_at      timestamptz   NOT NULL DEFAULT now(),
    updated_at      timestamptz   NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS projects_name_active_idx ON projects (lower(name)) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS projects_manager_idx ON projects (manager_id);
CREATE INDEX IF NOT EXISTS projects_status_idx ON projects (status);

DROP TRIGGER IF EXISTS projects_set_updated_at ON projects;
CREATE TRIGGER projects_set_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- milestones: key points in a project timeline, each with its own dates and hours.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS milestones (
    id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid          NOT NULL REFERENCES projects (id),
    name            text          NOT NULL,
    description     text          NOT NULL DEFAULT '',
    start_date      date          NOT NULL,
    due_date        date          NOT NULL,
    allocated_hours numeric(10,2) NOT NULL DEFAULT 0 CHECK (allocated_hours >= 0),
    status          text          NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending', 'in_progress', 'done')),
    completed_at    timestamptz,
    archived_at     timestamptz,
    created_at      timestamptz   NOT NULL DEFAULT now(),
    updated_at      timestamptz   NOT NULL DEFAULT now(),
    CHECK (due_date >= start_date)
);

CREATE INDEX IF NOT EXISTS milestones_project_idx ON milestones (project_id);

DROP TRIGGER IF EXISTS milestones_set_updated_at ON milestones;
CREATE TRIGGER milestones_set_updated_at BEFORE UPDATE ON milestones
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- project_assignments: an employee works on a project for a date range, giving
-- it their full 8-hour day. An employee may be on several projects over time but
-- ranges must not overlap (enforced in the service, under a row lock on the user).
-- Removing someone from a project archives the row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_assignments (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid        NOT NULL REFERENCES projects (id),
    user_id     uuid        NOT NULL REFERENCES users (id),
    start_date  date        NOT NULL,
    end_date    date        NOT NULL,
    assigned_by uuid        REFERENCES users (id),
    archived_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS project_assignments_active_idx
    ON project_assignments (project_id, user_id) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS project_assignments_user_idx ON project_assignments (user_id, start_date, end_date);

DROP TRIGGER IF EXISTS project_assignments_set_updated_at ON project_assignments;
CREATE TRIGGER project_assignments_set_updated_at BEFORE UPDATE ON project_assignments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- time_entries: hours an employee logged against a project (optionally a milestone).
-- The 8-hours-per-person-per-day cap is enforced in the service.
-- Labor cost = hours * users.salary at reporting time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS time_entries (
    id           uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid         NOT NULL REFERENCES projects (id),
    user_id      uuid         NOT NULL REFERENCES users (id),
    milestone_id uuid         REFERENCES milestones (id),
    work_date    date         NOT NULL,
    hours        numeric(5,2) NOT NULL CHECK (hours > 0 AND hours <= 8),
    notes        text         NOT NULL DEFAULT '',
    archived_at  timestamptz,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    updated_at   timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS time_entries_project_idx ON time_entries (project_id, work_date);
CREATE INDEX IF NOT EXISTS time_entries_user_idx ON time_entries (user_id, work_date);

DROP TRIGGER IF EXISTS time_entries_set_updated_at ON time_entries;
CREATE TRIGGER time_entries_set_updated_at BEFORE UPDATE ON time_entries
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- project_costs: non-labor spend (technology, licenses, vendors, ...).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_costs (
    id          uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid          NOT NULL REFERENCES projects (id),
    category    text          NOT NULL
                              CHECK (category IN ('technology', 'license', 'vendor', 'travel', 'other')),
    description text          NOT NULL,
    amount      numeric(14,2) NOT NULL CHECK (amount >= 0),
    incurred_on date          NOT NULL,
    created_by  uuid          REFERENCES users (id),
    archived_at timestamptz,
    created_at  timestamptz   NOT NULL DEFAULT now(),
    updated_at  timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS project_costs_project_idx ON project_costs (project_id, incurred_on);

DROP TRIGGER IF EXISTS project_costs_set_updated_at ON project_costs;
CREATE TRIGGER project_costs_set_updated_at BEFORE UPDATE ON project_costs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
