Schema v1 is defined by the SQLAlchemy models and created at startup via Base.metadata.create_all. For this local small application no destructive migration is run. Back up named db-data before modifying schemas.

Schema v2 (additive): joint studies — `joint_studies` (data_version, seed_base), `joint_members` (shared control + candidates, soft-withdraw), `joint_runs` (sealed snapshot, family seed, published flag, invalidation_reason). Created via Base.metadata.create_all at startup; existing v1 tables are untouched.
