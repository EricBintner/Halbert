# Scripts Directory

**Purpose**: Operational scripts for Cerebric development and deployment

---

## Current Scripts

### `demo_personas.sh`
**Purpose**: Demo script showing persona system (Phase 4)  
**Type**: Demo/testing  
**Usage**: `./demo_personas.sh`  
**Status**: Operational

### `package_phase5.sh`
**Purpose**: Package Phase 5 deliverables for handoff  
**Type**: One-time packaging (Phase 5 complete)  
**Usage**: `./package_phase5.sh`  
**Status**: Historical - Phase 5 already delivered  
**Action**: Can move to `maintenance/` folder

### `phase5_demo.py`
**Purpose**: Python demo of Phase 5 multi-model system  
**Type**: Demo/testing  
**Usage**: `python phase5_demo.py`  
**Status**: Operational demo

### `phase5_quickstart.sh`
**Purpose**: Quick start automation for Phase 5  
**Type**: Setup/testing  
**Usage**: `./phase5_quickstart.sh`  
**Status**: Operational

### `start_ingestion.sh`
**Purpose**: Start data ingestion services  
**Type**: Production/development  
**Usage**: `./start_ingestion.sh`  
**Status**: Operational

---

## Folder Structure

```
scripts/
├── demo_personas.sh          # Operational demo
├── phase5_demo.py            # Operational demo
├── phase5_quickstart.sh      # Operational setup
├── start_ingestion.sh        # Operational service
├── package_phase5.sh         # One-time (move to maintenance/)
└── maintenance/              # One-time/cleanup scripts
    └── (github prep scripts moved here)
```

---

## Maintenance Folder

**Purpose**: One-time use scripts that aren't needed for day-to-day work

**Examples**:
- GitHub preparation scripts
- One-time cleanup scripts
- Historical packaging scripts

**Git**: Added to `.gitignore` (not needed in public repo)

---

## Script Categories

### ✅ Keep in Root (Operational)
- **Demos**: `demo_personas.sh`, `phase5_demo.py`
- **Setup**: `phase5_quickstart.sh`
- **Services**: `start_ingestion.sh`

### 📁 Move to maintenance/ (One-time)
- **Historical**: `package_phase5.sh` (Phase 5 already packaged)
- **Cleanup**: GitHub prep scripts (already used)

---

## Adding New Scripts

**Operational scripts** (used regularly):
- Place in `scripts/` root
- Document in this README

**One-time scripts** (cleanup, migration, etc.):
- Place in `scripts/maintenance/`
- Add to .gitignore
- Document what it does and when it was used
