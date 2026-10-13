-- 002_milestone_work: milestones become the unit of work; time tracking is removed.
--
--   * Every Monday-Friday inside an assignment is one 8-hour shift. Hours and labor cost are
--     calculated from dates and users.salary, nothing is logged by hand.
--   * An employee is assigned to a MILESTONE (several people per milestone are fine), and one
--     person can only work one milestone per day (enforced in the service, under a row lock).
--   * A manager completes a milestone after ticking every deliverable; it then moves to the
--     archive, which only admins can see.
--   * Nothing is dropped: the old time and project-assignment tables are renamed and kept.

ALTER TABLE time_entries RENAME TO legacy_time_entries;
ALTER TABLE project_assignments RENAME TO legacy_project_assignments;

-- ---------------------------------------------------------------------------
-- milestones: planned budget, review note, new lifecycle (pending -> in_progress -> completed)
-- ---------------------------------------------------------------------------
ALTER TABLE milestones ADD COLUMN IF NOT EXISTS budget_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (budget_amount >= 0);
ALTER TABLE milestones ADD COLUMN IF NOT EXISTS review_note text NOT NULL DEFAULT '';
ALTER TABLE milestones ADD COLUMN IF NOT EXISTS reviewed_by uuid REFERENCES users (id);

ALTER TABLE milestones DROP CONSTRAINT IF EXISTS milestones_status_check;
UPDATE milestones SET status = 'completed' WHERE status = 'done';
ALTER TABLE milestones ADD CONSTRAINT milestones_status_check CHECK (status IN ('pending', 'in_progress', 'completed'));
-- A completed milestone is always archived.
UPDATE milestones SET archived_at = COALESCE(completed_at, now()) WHERE status = 'completed' AND archived_at IS NULL;

-- ---------------------------------------------------------------------------
-- working_days: Monday-Friday days in [a, b] inclusive (0 when b < a). One per 8-hour shift.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION working_days(a date, b date) RETURNS integer AS $$
    SELECT count(*)::int
    FROM generate_series(a::timestamp, b::timestamp, interval '1 day') AS d
    WHERE extract(isodow FROM d) < 6
$$ LANGUAGE sql IMMUTABLE;

-- ---------------------------------------------------------------------------
-- milestone_assignments: an employee works a milestone for a date range (default: its dates).
-- Ending an assignment (completion, removal) sets end_date; an assignment that never started
-- is archived instead.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS milestone_assignments (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    milestone_id uuid        NOT NULL REFERENCES milestones (id),
    user_id      uuid        NOT NULL REFERENCES users (id),
    start_date   date        NOT NULL,
    end_date     date        NOT NULL,
    assigned_by  uuid        REFERENCES users (id),
    archived_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (end_date >= start_date)
);

CREATE UNIQUE INDEX IF NOT EXISTS milestone_assignments_active_idx
    ON milestone_assignments (milestone_id, user_id) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS milestone_assignments_user_idx ON milestone_assignments (user_id, start_date, end_date);

DROP TRIGGER IF EXISTS milestone_assignments_set_updated_at ON milestone_assignments;
CREATE TRIGGER milestone_assignments_set_updated_at BEFORE UPDATE ON milestone_assignments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- deliverables: the checklist a manager reviews before completing a milestone.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deliverables (
    id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    milestone_id uuid        NOT NULL REFERENCES milestones (id),
    name         text        NOT NULL,
    description  text        NOT NULL DEFAULT '',
    done         boolean     NOT NULL DEFAULT false,
    done_at      timestamptz,
    done_by      uuid        REFERENCES users (id),
    archived_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS deliverables_milestone_idx ON deliverables (milestone_id);

DROP TRIGGER IF EXISTS deliverables_set_updated_at ON deliverables;
CREATE TRIGGER deliverables_set_updated_at BEFORE UPDATE ON deliverables
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
