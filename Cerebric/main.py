#!/usr/bin/env python3
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS_ROOT = os.path.normpath(os.path.join(ROOT, '..', 'docs'))

# Allow importing the local core package without installation
REPO_ROOT = os.path.normpath(os.path.join(ROOT, '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from cerebric_core.cerebric_core.ingestion.runner import run_journald
    from cerebric_core.cerebric_core.ingestion.hwmon_runner import run_hwmon
    from cerebric_core.cerebric_core.config.snapshot import snapshot as snapshot_configs
    from cerebric_core.cerebric_core.config.watcher import ConfigWatcher
    from cerebric_core.cerebric_core.config.drift import diff_snapshots
    from cerebric_core.cerebric_core.obs.dashboard import build_all as build_dashboard_all
    from cerebric_core.cerebric_core.index.chroma_index import Index as CerebricIndex
    from cerebric_core.cerebric_core.utils.paths import data_subdir, config_dir
    from cerebric_core.cerebric_core.eval.golden import run_all as run_golden
    from cerebric_core.cerebric_core.config.indexer import index_all as index_configs_all
    from cerebric_core.cerebric_core.runtime.langgraph_engine import LGEngine
    from cerebric_core.cerebric_core.runtime.engine import Engine as FallbackEngine
    from cerebric_core.cerebric_core.policy.loader import load_policy
    from cerebric_core.cerebric_core.scheduler.engine import SchedulerEngine
    from cerebric_core.cerebric_core.scheduler.job import Job
    from cerebric_core.cerebric_core.model.loader import ModelManager, ModelConfig
    from cerebric_core.cerebric_core.model.prompt_manager import PromptManager, PromptMode
    from cerebric_core.cerebric_core.memory.retrieval import MemoryRetrieval
    from cerebric_core.cerebric_core.memory.writer import MemoryWriter
    from cerebric_core.cerebric_core.scheduler.executor import AutonomousExecutor
    from cerebric_core.cerebric_core.scheduler.autonomous_tasks import create_autonomous_task
    from cerebric_core.cerebric_core.approval.engine import ApprovalEngine, ApprovalRequest
    from cerebric_core.cerebric_core.approval.simulator import DryRunSimulator
    from cerebric_core.cerebric_core.dashboard.app import create_app as create_dashboard_app
    from cerebric_core.cerebric_core.autonomy import GuardrailEnforcer, AnomalyDetector, RecoveryExecutor
    from cerebric_core.cerebric_core.persona import PersonaManager, Persona, PersonaSwitchError, MemoryPurge, ContextDetector
    from cerebric_core.cerebric_core.model import LoRAManager, LoRANotFoundError, LoRADownloadError, ModelRouter, TaskType
    from cerebric_core.cerebric_core.model.hardware_detector import HardwareDetector
    from cerebric_core.cerebric_core.model.config_wizard import ConfigWizard
except Exception:
    # Soft-fail import; commands will warn if invoked without deps
    run_journald = None  # type: ignore
    run_hwmon = None  # type: ignore
    snapshot_configs = None  # type: ignore
    ConfigWatcher = None  # type: ignore
    diff_snapshots = None  # type: ignore
    build_dashboard_all = None  # type: ignore
    CerebricIndex = None  # type: ignore
    data_subdir = None  # type: ignore
    config_dir = None  # type: ignore
    run_golden = None  # type: ignore
    index_configs_all = None  # type: ignore
    LGEngine = None  # type: ignore
    FallbackEngine = None  # type: ignore
    load_policy = None  # type: ignore
    SchedulerEngine = None  # type: ignore
    Job = None  # type: ignore
    ModelManager = None  # type: ignore
    ModelConfig = None  # type: ignore
    PromptManager = None  # type: ignore
    PromptMode = None  # type: ignore
    MemoryRetrieval = None  # type: ignore
    MemoryWriter = None  # type: ignore
    AutonomousExecutor = None  # type: ignore
    create_autonomous_task = None  # type: ignore
    ApprovalEngine = None  # type: ignore
    ApprovalRequest = None  # type: ignore
    DryRunSimulator = None  # type: ignore
    create_dashboard_app = None  # type: ignore
    GuardrailEnforcer = None  # type: ignore
    AnomalyDetector = None  # type: ignore
    RecoveryExecutor = None  # type: ignore
    PersonaManager = None  # type: ignore
    Persona = None  # type: ignore
    PersonaSwitchError = None  # type: ignore
    MemoryPurge = None  # type: ignore
    ContextDetector = None  # type: ignore
    LoRAManager = None  # type: ignore
    LoRANotFoundError = None  # type: ignore
    LoRADownloadError = None  # type: ignore
    ModelRouter = None  # type: ignore
    TaskType = None  # type: ignore


def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"File not found: {path}"


def cmd_info(args):
    print("Cerebric — Local-First Multi-Agent OS Companion")
    print("Phase 1 (Alpha): Observability Assistant")
    print("Offline-first, confirm-by-default, auditable tools")
    print()
    print("See docs/Phase1 for Phase 1 planning and roadmap.")


def cmd_roadmap(args):
    # Show the consolidated Phase 1 roadmap from docs
    print(read_text(os.path.join(DOCS_ROOT, 'Phase1', 'ROADMAP.md')))


def cmd_show(args):
    path = os.path.join(ROOT, args.path)
    print(read_text(path))

def cmd_showdoc(args):
    # Show a file under docs/ (e.g., Phase1/ROADMAP.md)
    path = os.path.join(DOCS_ROOT, args.path)
    print(read_text(path))


def cmd_ingest_journald(args):
    # Prefer FHS/XDG config path if present
    default_cfg = None
    if config_dir is not None:
        cand = os.path.join(config_dir(), 'ingestion.yml')
        if os.path.exists(cand):
            default_cfg = cand
    cfg = args.config or default_cfg or os.path.join(os.path.dirname(ROOT), 'config', 'ingestion.yml')
    schema = args.schema or os.path.join(DOCS_ROOT, 'Phase1', 'schemas', 'telemetry-event.schema.json')
    if run_journald is None:
        print('cerebric_core not available or dependencies missing (pyyaml).')
        return
    run_journald(cfg, schema_path=schema)


def cmd_snapshot_configs(args):
    default_manifest = None
    if config_dir is not None:
        cand = os.path.join(config_dir(), 'config-registry.yml')
        if os.path.exists(cand):
            default_manifest = cand
    manifest = args.manifest or default_manifest or os.path.join(os.path.dirname(ROOT), 'config', 'config-registry.yml')
    if snapshot_configs is None:
        print('cerebric_core not available or dependencies missing (pyyaml).')
        return
    result = snapshot_configs(manifest)
    print(f"Snapshotted {len(result)} files.")


def cmd_watch_configs(args):
    import time
    default_manifest = None
    if config_dir is not None:
        cand = os.path.join(config_dir(), 'config-registry.yml')
        if os.path.exists(cand):
            default_manifest = cand
    manifest = args.manifest or default_manifest or os.path.join(os.path.dirname(ROOT), 'config', 'config-registry.yml')
    interval = int(args.interval)
    if ConfigWatcher is None:
        print('cerebric_core not available or dependencies missing (watchdog/pyyaml).')
        return
    def _on_snapshot(res):
        print(f"[configs] snapshot {len(res)} entries")
    watcher = ConfigWatcher(manifest_path=manifest, on_snapshot=_on_snapshot, interval_s=interval)
    watcher.start()
    print('Watching configs. Press Ctrl+C to stop...')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()


def _load_snapshot(path: str):
    import json
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _find_snapshots_dir() -> str:
    if data_subdir is not None:
        try:
            return data_subdir('config', 'snapshots')
        except Exception:
            pass
    return os.path.join(os.path.dirname(ROOT), 'data', 'config', 'snapshots')


def _latest_and_prev_snapshots(snap_dir: str):
    files = [f for f in os.listdir(snap_dir) if f.endswith('.json') and f != 'latest.json']
    files.sort()
    if len(files) < 2:
        return None, None
    return os.path.join(snap_dir, files[-2]), os.path.join(snap_dir, files[-1])


def cmd_diff_configs(args):
    if diff_snapshots is None:
        print('cerebric_core not available.')
        return
    prev = args.prev
    curr = args.curr
    if not prev or not curr:
        snap_dir = _find_snapshots_dir()
        if not os.path.isdir(snap_dir):
            print('No snapshots directory found. Run snapshot-configs first.')
            return
        p, c = _latest_and_prev_snapshots(snap_dir)
        if not p or not c:
            print('Not enough snapshots to diff. Run snapshot-configs twice.')
            return
        prev, curr = p, c
    p_data = _load_snapshot(prev)
    c_data = _load_snapshot(curr)
    changes = diff_snapshots(p_data, c_data)
    print(f"Changes: {len(changes)}")
    for ch in changes[:50]:
        path = ch.get('path')
        change = ch.get('change')
        print(f"- {change}: {path}")


def cmd_build_dashboard(args):
    if build_dashboard_all is None:
        print('cerebric_core not available.')
        return
    paths = build_dashboard_all()
    print('\n'.join(paths))


def cmd_index_query(args):
    if CerebricIndex is None:
        print('cerebric_core not available.')
        return
    idx = CerebricIndex(data_subdir('index') if data_subdir else None)
    res = idx.query(args.text, k=int(args.k))
    for r in res:
        print(r)


def cmd_eval_golden(args):
    if run_golden is None:
        print('cerebric_core not available.')
        return
    out = run_golden()
    print(out)


def cmd_runtime_tick(args):
    # Prefer LangGraph engine when available
    state = {}
    if LGEngine is not None:
        try:
            lg = LGEngine()
            if lg.available():
                state = lg.run_once({})
                print(state)
                return
        except Exception:
            pass
    if FallbackEngine is None:
        print("runtime engine unavailable")
        return
    eng = FallbackEngine()
    s = eng.tick({})
    print(s.__dict__ if hasattr(s, "__dict__") else s)


def cmd_index_configs(args):
    if index_configs_all is None:
        print('cerebric_core not available.')
        return
    count = index_configs_all()
    print(f"Indexed {count} config records.")


def cmd_policy_show(args):
    if load_policy is None:
        print('policy engine not available')
        return
    pol = load_policy()
    import json as _json
    print(_json.dumps(pol, indent=2, ensure_ascii=False))


def cmd_policy_eval(args):
    if load_policy is None:
        print('policy engine not available')
        return
    pol = load_policy()
    import json as _json
    try:
        with open(args.inputs, 'r', encoding='utf-8') as f:
            inputs = _json.load(f)
    except Exception as e:
        print(f"failed to read inputs: {e}")
        return
    from cerebric_core.cerebric_core.policy.engine import decide as _decide
    d = _decide(pol, args.tool, is_apply=True, ctx={"inputs": inputs})
    print(_json.dumps({"tool": args.tool, "allow": d.allow, "reason": d.reason}, indent=2, ensure_ascii=False))


def cmd_scheduler_add(args):
    if SchedulerEngine is None or Job is None:
        print('scheduler not available')
        return
    import json as _json
    try:
        with open(args.inputs, 'r', encoding='utf-8') as f:
            inputs = _json.load(f)
    except Exception as e:
        print(f"failed to read inputs: {e}")
        return
    eng = SchedulerEngine()
    job = Job(
        id=args.id,
        task=args.task,
        schedule=args.schedule,
        priority=int(args.priority),
        inputs=inputs,
    )
    eng.add_job(job)
    print(f"Added job {job.id}")


def cmd_scheduler_list(args):
    if SchedulerEngine is None:
        print('scheduler not available')
        return
    import json as _json
    eng = SchedulerEngine()
    jobs = eng.list_jobs(state=args.state if args.state else None)
    for j in jobs:
        print(_json.dumps(j.__dict__, ensure_ascii=False))


def cmd_scheduler_cancel(args):
    if SchedulerEngine is None:
        print('scheduler not available')
        return
    eng = SchedulerEngine()
    ok = eng.cancel_job(args.id)
    if ok:
        print(f"Cancelled job {args.id}")
    else:
        print(f"Job {args.id} not found or already terminal")


def cmd_model_status(args):
    """Show model status (Phase 3 M1)."""
    if ModelManager is None:
        print('model not available (install ollama or llama-cpp-python)')
        return
    
    try:
        mgr = ModelManager()
        status = mgr.get_status()
        
        import json as _json
        print(_json.dumps(status, indent=2))
    except Exception as e:
        print(f"Error getting model status: {e}")


def cmd_model_test(args):
    """Test model with a simple prompt (Phase 3 M1)."""
    if ModelManager is None or PromptManager is None:
        print('model not available (install ollama or llama-cpp-python)')
        return
    
    try:
        import time
        
        mgr = ModelManager()
        pm = PromptManager()
        
        # Build system prompt
        system_prompt = pm.build_prompt(PromptMode.INTERACTIVE)
        
        # Combine with user prompt
        full_prompt = f"{system_prompt}\n\nUser: {args.prompt}\n\nAssistant:"
        
        print(f"Generating response for: {args.prompt}")
        print("---")
        
        start = time.time()
        response = mgr.generate(full_prompt, max_tokens=args.max_tokens or 256)
        duration = time.time() - start
        
        print(response)
        print("---")
        print(f"Generated in {duration:.2f}s")
        
        # Estimate confidence
        confidence = mgr.estimate_confidence(response)
        print(f"Confidence: {confidence:.2f}")
        
    except Exception as e:
        print(f"Error testing model: {e}")
        import traceback
        traceback.print_exc()


def cmd_prompt_show(args):
    """Show system prompt for a given mode (Phase 3 M1)."""
    if PromptManager is None:
        print('prompt manager not available')
        return
    
    try:
        pm = PromptManager()
        
        # Parse mode
        try:
            mode = PromptMode(args.mode)
        except ValueError:
            print(f"Unknown mode: {args.mode}")
            print(f"Available modes: {', '.join([m.value for m in PromptMode])}")
            return
        
        # Build and display prompt
        prompt = pm.build_prompt(mode, task_context=args.context)
        
        print(f"=== Prompt for mode: {mode.value} ===")
        print(pm.get_mode_description(mode))
        print()
        print(prompt)
        print()
        print(f"=== Validation: {'PASS' if pm.validate_prompt(prompt) else 'FAIL'} ===")
        
    except Exception as e:
        print(f"Error showing prompt: {e}")


def cmd_prompt_init(args):
    """Initialize default prompt configuration (Phase 3 M1)."""
    if PromptManager is None:
        print('prompt manager not available')
        return
    
    try:
        pm = PromptManager()
        pm.create_default_config()
        print(f"Prompt configuration created at: {pm.config_dir / 'prompts'}")
        print("Edit prompt files to customize (see README.md)")
    except Exception as e:
        print(f"Error initializing prompts: {e}")


def cmd_memory_query(args):
    """Query memory (Phase 3 M2)."""
    if MemoryRetrieval is None:
        print('memory not available')
        return
    
    try:
        mem = MemoryRetrieval()
        results = mem.retrieve_from(args.subdir, args.query, k=args.limit or 5)
        
        import json as _json
        print(f"Found {len(results)} results for query: {args.query}")
        print("---")
        
        for i, result in enumerate(results, 1):
            print(f"\n[{i}] Score: {result.get('_score', 0):.2f} | Source: {result.get('_source', 'unknown')}")
            print(f"    {result.get('text', result.get('summary', 'No text'))[:200]}")
        
        if args.json:
            print("\n--- Full JSON ---")
            print(_json.dumps(results, indent=2))
    
    except Exception as e:
        print(f"Error querying memory: {e}")


def cmd_memory_stats(args):
    """Show memory statistics (Phase 3 M2)."""
    if MemoryRetrieval is None:
        print('memory not available')
        return
    
    try:
        mem = MemoryRetrieval()
        stats = mem.get_stats()
        
        import json as _json
        print(_json.dumps(stats, indent=2))
    
    except Exception as e:
        print(f"Error getting memory stats: {e}")


def cmd_memory_write(args):
    """Write test entry to memory (Phase 3 M2)."""
    if MemoryWriter is None:
        print('memory not available')
        return
    
    try:
        import json as _json
        
        writer = MemoryWriter()
        
        # Parse entry from JSON
        entry = _json.loads(args.entry)
        
        # Write based on type
        if args.subdir == 'core':
            ok = writer.write_core_knowledge(entry)
        elif args.subdir == 'runtime':
            ok = writer.write_action_outcome(entry)
        else:
            print(f"Unknown subdir: {args.subdir}")
            return
        
        if ok:
            print(f"Entry written to {args.subdir}")
        else:
            print(f"Failed to write entry")
    
    except Exception as e:
        print(f"Error writing memory: {e}")


def cmd_executor_status(args):
    """Show autonomous executor status (Phase 3 M3)."""
    if AutonomousExecutor is None:
        print('autonomous executor not available (install apscheduler: pip install apscheduler)')
        return
    
    try:
        executor = AutonomousExecutor()
        status = executor.get_status()
        
        import json as _json
        print(_json.dumps(status, indent=2))
    
    except Exception as e:
        print(f"Error getting executor status: {e}")


def cmd_executor_schedule(args):
    """Schedule a cron job (Phase 3 M3)."""
    if AutonomousExecutor is None:
        print('autonomous executor not available (install apscheduler: pip install apscheduler)')
        return
    
    try:
        import json as _json
        
        # Parse cron expression
        cron_expr = _json.loads(args.cron)
        
        # Create dummy task function
        def dummy_task():
            print(f"Executing task: {args.job_id}")
            return "success"
        
        executor = AutonomousExecutor()
        executor.start()
        
        job_id = executor.schedule_cron_job(
            job_id=args.job_id,
            task_func=dummy_task,
            cron_expr=cron_expr,
            description=args.description or args.job_id
        )
        
        print(f"Scheduled job: {job_id}")
        print(f"Cron expression: {cron_expr}")
        print("Use 'executor-list' to see scheduled jobs")
        
        # Keep executor running
        if args.daemon:
            print("Running in daemon mode. Press Ctrl+C to stop...")
            import time
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                executor.stop()
                print("Executor stopped")
        else:
            executor.stop(wait=False)
    
    except Exception as e:
        print(f"Error scheduling job: {e}")
        import traceback
        traceback.print_exc()


def cmd_executor_list(args):
    """List scheduled jobs (Phase 3 M3)."""
    if AutonomousExecutor is None:
        print('autonomous executor not available (install apscheduler: pip install apscheduler)')
        return
    
    try:
        executor = AutonomousExecutor()
        executor.start()
        
        jobs = executor.get_scheduled_jobs()
        
        if not jobs:
            print("No scheduled jobs")
            return
        
        import json as _json
        print(_json.dumps(jobs, indent=2))
        
        executor.stop(wait=False)
    
    except Exception as e:
        print(f"Error listing jobs: {e}")


def cmd_executor_cancel(args):
    """Cancel a scheduled job (Phase 3 M3)."""
    if AutonomousExecutor is None:
        print('autonomous executor not available (install apscheduler: pip install apscheduler)')
        return
    
    try:
        executor = AutonomousExecutor()
        executor.start()
        
        success = executor.cancel_job(args.job_id)
        
        if success:
            print(f"Cancelled job: {args.job_id}")
        else:
            print(f"Job not found or already completed: {args.job_id}")
        
        executor.stop(wait=False)
    
    except Exception as e:
        print(f"Error cancelling job: {e}")


def cmd_approval_list(args):
    """List pending approval requests (Phase 3 M4)."""
    if ApprovalEngine is None:
        print('approval engine not available')
        return
    
    try:
        engine = ApprovalEngine()
        pending = engine.get_pending_requests()
        
        if not pending:
            print("No pending approval requests")
            return
        
        import json as _json
        
        print(f"\nPending Approval Requests: {len(pending)}")
        print("=" * 70)
        
        for request in pending:
            print(f"\nID: {request.id}")
            print(f"Task: {request.task}")
            print(f"Action: {request.action}")
            print(f"Confidence: {request.confidence:.2f}")
            print(f"Risk Level: {request.risk_level}")
            print(f"Requested: {request.requested_at}")
            print("-" * 70)
    
    except Exception as e:
        print(f"Error listing approval requests: {e}")


def cmd_approval_history(args):
    """Show approval history (Phase 3 M4)."""
    if ApprovalEngine is None:
        print('approval engine not available')
        return
    
    try:
        import json as _json
        
        engine = ApprovalEngine()
        history = engine.get_approval_history(
            limit=args.limit,
            approved_only=args.approved_only
        )
        
        if not history:
            print("No approval history")
            return
        
        print(f"\nApproval History (last {len(history)} records):")
        print("=" * 70)
        
        for record in history:
            print(f"\nRequest ID: {record.get('request_id')}")
            print(f"Approved: {record.get('approved')}")
            print(f"Decided By: {record.get('decided_by')}")
            print(f"Decided At: {record.get('decided_at')}")
            if record.get('reason'):
                print(f"Reason: {record['reason']}")
            print("-" * 70)
    
    except Exception as e:
        print(f"Error showing approval history: {e}")


def cmd_dashboard_serve(args):
    """Start Cerebric dashboard server (Phase 3 M5)."""
    if create_dashboard_app is None:
        print('dashboard not available (install: pip install fastapi uvicorn)')
        return
    
    try:
        print("🚀 Starting Cerebric Dashboard...")
        print(f"   Host: {args.host}")
        print(f"   Port: {args.port}")
        print(f"   URL: http://{args.host}:{args.port}")
        print()
        print("   API docs: http://{args.host}:{args.port}/docs")
        print("   WebSocket: ws://{args.host}:{args.port}/ws")
        print()
        print("Press Ctrl+C to stop\n")
        
        import uvicorn
        
        # Create app
        app = create_dashboard_app(enable_cors=True)
        
        # Run server
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info"
        )
    
    except KeyboardInterrupt:
        print("\n\nDashboard stopped")
    except Exception as e:
        print(f"Error starting dashboard: {e}")
        import traceback
        traceback.print_exc()


def cmd_autonomy_status(args):
    """Show autonomy guardrail status (Phase 3 M6)."""
    if GuardrailEnforcer is None:
        print('autonomy guardrails not available')
        return
    
    try:
        enforcer = GuardrailEnforcer()
        
        print("\n" + "=" * 60)
        print("AUTONOMY GUARDRAILS STATUS")
        print("=" * 60)
        print()
        print(f"Safe Mode: {'🔴 ACTIVE' if enforcer.is_safe_mode_active() else '🟢 Inactive'}")
        print()
        print("Confidence Thresholds:")
        print(f"  Auto-execute: {enforcer.config['confidence']['min_auto_execute']:.0%}")
        print(f"  Require approval: {enforcer.config['confidence']['min_approval_execute']:.0%}")
        print()
        print("Resource Budgets (per job):")
        print(f"  CPU: {enforcer.config['budgets']['cpu_percent_max']}%")
        print(f"  Memory: {enforcer.config['budgets']['memory_mb_max']} MB")
        print(f"  Time: {enforcer.config['budgets']['time_minutes_max']} minutes")
        print(f"  Frequency: {enforcer.config['budgets']['frequency_per_hour_max']} jobs/hour")
        print()
        print("Anomaly Detection:")
        print(f"  CPU spike threshold: {enforcer.config['anomalies']['cpu_spike_threshold']}%")
        print(f"  Memory leak threshold: {enforcer.config['anomalies']['memory_leak_mb']} MB")
        print(f"  Repeated failures: {enforcer.config['anomalies']['repeated_failures']}")
        print(f"  Error rate threshold: {enforcer.config['anomalies']['error_rate_threshold']:.0%}")
        print()
        print("=" * 60)
    
    except Exception as e:
        print(f"Error getting autonomy status: {e}")
        import traceback
        traceback.print_exc()


def cmd_autonomy_pause(args):
    """Pause autonomous operations (safe-mode) (Phase 3 M6)."""
    if GuardrailEnforcer is None:
        print('autonomy guardrails not available')
        return
    
    try:
        enforcer = GuardrailEnforcer()
        enforcer.enter_safe_mode(args.reason)
        
        print("\n🔴 AUTONOMY PAUSED (Safe Mode Activated)")
        print(f"   Reason: {args.reason}")
        print()
        print("   All autonomous operations are suspended.")
        print(f"   Resume with: autonomy-resume --user $(whoami)")
        print()
    
    except Exception as e:
        print(f"Error pausing autonomy: {e}")


def cmd_autonomy_resume(args):
    """Resume autonomous operations (Phase 3 M6)."""
    if GuardrailEnforcer is None:
        print('autonomy guardrails not available')
        return
    
    try:
        enforcer = GuardrailEnforcer()
        
        if not enforcer.is_safe_mode_active():
            print("\n⚠ Autonomy is not paused (safe-mode is not active)")
            return
        
        enforcer.exit_safe_mode(args.user)
        
        print("\n🟢 AUTONOMY RESUMED")
        print(f"   Authorized by: {args.user}")
        print()
        print("   Autonomous operations are now active.")
        print()
    
    except Exception as e:
        print(f"Error resuming autonomy: {e}")


def cmd_autonomy_anomalies(args):
    """View detected anomalies (Phase 3 M6)."""
    if AnomalyDetector is None:
        print('autonomy guardrails not available')
        return
    
    try:
        import yaml
        
        with open("config/autonomy.yml") as f:
            config = yaml.safe_load(f)
        
        detector = AnomalyDetector(config["anomalies"])
        anomalies = detector.get_recent_anomalies(hours=args.hours)
        
        print(f"\nAnomalies (last {args.hours} hours)")
        print("=" * 60)
        
        if not anomalies:
            print("\n✓ No anomalies detected\n")
            return
        
        for a in anomalies:
            severity_icon = "🔴" if a.severity == "critical" else "⚠"
            print(f"\n{severity_icon} [{a.severity.upper()}] {a.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Type: {a.anomaly_type}")
            print(f"   {a.description}")
            if a.metrics:
                print(f"   Metrics: {a.metrics}")
        
        print("\n" + "=" * 60 + "\n")
    
    except Exception as e:
        print(f"Error viewing anomalies: {e}")
        import traceback
        traceback.print_exc()


def cmd_autonomy_recovery(args):
    """View recovery action history (Phase 3 M6)."""
    if RecoveryExecutor is None:
        print('autonomy guardrails not available')
        return
    
    try:
        import yaml
        
        with open("config/autonomy.yml") as f:
            config = yaml.safe_load(f)
        
        executor = RecoveryExecutor(config["recovery"])
        history = executor.get_history(limit=args.limit)
        
        print(f"\nRecovery Actions (last {args.limit})")
        print("=" * 60)
        
        if not history:
            print("\n✓ No recovery actions recorded\n")
            return
        
        for r in history:
            status_icon = "✅" if r.success else "❌"
            print(f"\n{status_icon} [{r.action.value}] {r.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   {r.message}")
            if r.details:
                print(f"   Details: {r.details}")
        
        print("\n" + "=" * 60 + "\n")
    
    except Exception as e:
        print(f"Error viewing recovery history: {e}")
        import traceback
        traceback.print_exc()


def cmd_persona_list(args):
    """List available personas (Phase 4 M1)."""
    if PersonaManager is None:
        print('persona system not available')
        return
    
    try:
        manager = PersonaManager()
        personas = manager.list_personas()
        
        print("\nAvailable Personas")
        print("=" * 60)
        
        for p in personas:
            status_icon = "●" if p['active'] else "○"
            enabled_text = "" if p['enabled'] else " (disabled)"
            
            print(f"\n{status_icon} {p['icon']} {p['name']}{enabled_text}")
            print(f"   ID: {p['id']}")
            print(f"   {p['description']}")
            print(f"   Memory: {p['memory_dir']}")
            
            if p.get('note'):
                print(f"   Note: {p['note']}")
        
        print("\n" + "=" * 60 + "\n")
    
    except Exception as e:
        print(f"Error listing personas: {e}")
        import traceback
        traceback.print_exc()


def cmd_persona_status(args):
    """Show active persona status (Phase 4 M1)."""
    if PersonaManager is None:
        print('persona system not available')
        return
    
    try:
        manager = PersonaManager()
        state = manager.get_state()
        
        print("\n" + "=" * 60)
        print("PERSONA STATUS")
        print("=" * 60)
        print(f"Active Persona: {state.active_persona.value}")
        print(f"Memory Directory: {state.memory_dir}")
        print(f"LoRA: {state.lora or 'None (base model)'}")
        print(f"Switched At: {state.switched_at}")
        print(f"Switched By: {state.switched_by}")
        print("=" * 60 + "\n")
    
    except Exception as e:
        print(f"Error getting persona status: {e}")


def cmd_persona_switch(args):
    """Switch to a different persona (Phase 4 M1)."""
    if PersonaManager is None or Persona is None:
        print('persona system not available')
        return
    
    try:
        manager = PersonaManager()
        
        # Parse target persona
        try:
            target_persona = Persona(args.to)
        except ValueError:
            print(f"Invalid persona: {args.to}")
            print(f"Available: it_admin, friend, custom")
            return
        
        # Show confirmation if not using --confirm
        if not args.confirm:
            current = manager.get_active_persona()
            print(f"\nSwitch from {current.value} to {target_persona.value}?")
            print("Run with --confirm to execute")
            return
        
        # Execute switch
        success = manager.switch_to(
            target_persona,
            user=args.user or "cli_user"
        )
        
        if success:
            print(f"\n✅ Switched to {target_persona.value} persona")
            print(f"   Memory: {manager.get_memory_dir()}")
            print()
        else:
            print(f"\n❌ Failed to switch to {target_persona.value}")
    
    except PersonaSwitchError as e:
        print(f"\n❌ Persona switch failed: {e}")
    except Exception as e:
        print(f"Error switching persona: {e}")
        import traceback
        traceback.print_exc()


def cmd_memory_purge(args):
    """Purge persona-specific memory (Phase 4 M1)."""
    if MemoryPurge is None:
        print('memory purge not available')
        return
    
    try:
        purge = MemoryPurge()
        
        # Preview purge
        confirmation = purge.preview_purge(args.persona)
        
        print("\n" + "=" * 60)
        print(f"PURGE PREVIEW: {args.persona} persona")
        print("=" * 60)
        print(f"Estimated entries: {confirmation.estimated_entries}")
        print(f"Estimated size: {confirmation.estimated_size_mb} MB")
        print()
        print("Will delete:")
        for item in confirmation.will_delete[:5]:  # Show first 5
            print(f"  - {item}")
        if len(confirmation.will_delete) > 5:
            print(f"  ... and {len(confirmation.will_delete) - 5} more files")
        print()
        print("Will preserve:")
        for item in confirmation.will_preserve:
            print(f"  ✓ {item}")
        print("=" * 60)
        
        # Check confirmation flag
        if not args.confirm:
            print("\n⚠ Run with --confirm to execute purge")
            return
        
        # Execute purge
        result = purge.execute_purge(
            args.persona,
            user=args.user or "cli_user",
            export_before=not args.no_export
        )
        
        if result['success']:
            print(f"\n✅ Memory purged for {args.persona} persona")
            print(f"   Deleted: {result['entries_deleted']} entries ({result['size_mb_deleted']} MB)")
            if result['exported']:
                print(f"   Exported to: {result['export_path']}")
            print()
        else:
            print(f"\n❌ Purge failed: {result.get('error')}")
    
    except ValueError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"Error purging memory: {e}")
        import traceback
        traceback.print_exc()


def cmd_lora_list(args):
    """List available LoRA adapters (Phase 4 M2)."""  
    if LoRAManager is None:
        print('LoRA manager not available')
        return
    
    try:
        manager = LoRAManager()
        
        # Filter by category if specified
        category = args.category if hasattr(args, 'category') and args.category else None
        loras = manager.list_loras(category=category)
        
        if not loras:
            print("\nNo LoRAs available")
            if category:
                print(f"   (filtered by category: {category})")
            print()
            return
        
        print("\nAvailable LoRA Adapters")
        print("=" * 70)
        
        for lora in loras:
            active_mark = " (ACTIVE)" if lora.get('active') else ""
            cached_mark = " ✓" if lora.get('cached') else ""
            
            print(f"\n[{lora['category'].upper()}] {lora['key']}{active_mark}{cached_mark}")
            print(f"   Description: {lora.get('description', 'No description')}")
            print(f"   Persona: {lora.get('persona', 'N/A')}")
            print(f"   Size: {lora.get('size_mb', 0)} MB")
            print(f"   Format: {lora.get('format', 'N/A')}")
            
            if lora.get('tested'):
                print(f"   Status: ✓ Verified")
            else:
                print(f"   Status: ⚠ Experimental (not verified)")
            
            if lora.get('note'):
                print(f"   Note: {lora['note']}")
        
        print("\n" + "=" * 70)
        print("\nLegend: ✓ = cached locally, ACTIVE = currently loaded")
        print()
    
    except Exception as e:
        print(f"Error listing LoRAs: {e}")
        import traceback
        traceback.print_exc()


def cmd_lora_info(args):
    """Show detailed info for a specific LoRA (Phase 4 M2)."""  
    if LoRAManager is None:
        print('LoRA manager not available')
        return
    
    try:
        manager = LoRAManager()
        lora_info = manager.get_lora_info(args.lora_key)
        
        print("\n" + "=" * 70)
        print(f"LoRA: {lora_info['key']}")
        print("=" * 70)
        print(f"Category: {lora_info['category']}")
        print(f"Description: {lora_info.get('description', 'N/A')}")
        print(f"Persona: {lora_info.get('persona', 'N/A')}")
        print(f"Size: {lora_info.get('size_mb', 0)} MB")
        print(f"Format: {lora_info.get('format', 'N/A')}")
        print(f"Source: {lora_info.get('source', 'N/A')}")
        print(f"Tested: {'Yes' if lora_info.get('tested') else 'No'}")
        print(f"Cached: {'Yes' if lora_info.get('cached') else 'No'}")
        print(f"Active: {'Yes' if lora_info.get('active') else 'No'}")
        
        if lora_info.get('note'):
            print(f"\nNote: {lora_info['note']}")
        
        print("=" * 70 + "\n")
    
    except LoRANotFoundError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"Error getting LoRA info: {e}")
        import traceback
        traceback.print_exc()


def cmd_lora_set(args):
    """Set LoRA for a persona (Phase 4 M2)."""  
    if LoRAManager is None or PersonaManager is None:
        print('LoRA manager or PersonaManager not available')
        return
    
    try:
        lora_mgr = LoRAManager()
        persona_mgr = PersonaManager()
        
        # Get LoRA info
        lora_info = lora_mgr.get_lora_info(args.lora_key)
        
        print(f"\nSetting LoRA '{args.lora_key}' for persona '{args.persona}'...")
        print(f"   Description: {lora_info.get('description')}")
        print(f"   Size: {lora_info.get('size_mb')} MB")
        
        # Download if not cached
        if not lora_info.get('cached'):
            print(f"\n   Downloading from {lora_info.get('source')}...")
            cache_path = lora_mgr.ensure_cached(args.lora_key)
            print(f"   ✓ Downloaded to {cache_path}")
        
        # Set active
        lora_mgr.set_active_lora(args.lora_key)
        
        # Update persona state if persona matches
        current_persona = persona_mgr.get_active_persona()
        if current_persona.value == args.persona:
            persona_mgr.switch_to(current_persona, user="cli", lora=args.lora_key)
        
        print(f"\n✅ LoRA '{args.lora_key}' set for {args.persona} persona")
        print(f"   Switch to {args.persona} persona to use this LoRA")
        print()
    
    except LoRANotFoundError as e:
        print(f"\n❌ {e}")
    except LoRADownloadError as e:
        print(f"\n❌ Download failed: {e}")
    except Exception as e:
        print(f"Error setting LoRA: {e}")
        import traceback
        traceback.print_exc()


def cmd_context_detect(args):
    """Detect current user context from running apps (Phase 4 M4)."""  
    if ContextDetector is None:
        print('Context detector not available')
        return
    
    try:
        detector = ContextDetector()
        
        print("\nDetecting current context...\n")
        
        # Get running processes
        processes = detector.get_running_processes()
        print(f"Found {len(processes)} running processes")
        
        # Detect context
        signal = detector.detect_context()
        
        if signal:
            print("\n" + "=" * 60)
            print("CONTEXT DETECTED")
            print("=" * 60)
            print(f"Context Type: {signal.context_type}")
            print(f"Confidence: {signal.confidence * 100:.0f}%")
            print(f"Suggested Persona: {signal.suggested_persona}")
            print(f"Reason: {signal.reason}")
            print(f"\nSource Processes:")
            for proc in signal.source_processes:
                print(f"  - {proc}")
            print("=" * 60)
            
            # Check if should suggest
            if detector.should_suggest(signal):
                print("\n✅ Suggestion would be shown to user")
                print(f"   Switch to '{signal.suggested_persona}' persona?")
            else:
                print("\n⚠ Suggestion suppressed (cooldown, DND, or low confidence)")
            
            print()
        else:
            print("\n⚠ No clear context detected")
            print("   Staying with current persona\n")
    
    except Exception as e:
        print(f"Error detecting context: {e}")
        import traceback
        traceback.print_exc()


def cmd_context_prefs(args):
    """Show or update context detection preferences (Phase 4 M4)."""  
    if ContextDetector is None:
        print('Context detector not available')
        return
    
    try:
        detector = ContextDetector()
        
        # If no updates, just show current preferences
        if not any([args.enabled, args.disable, args.auto_switch, args.no_auto_switch]):
            print("\n" + "=" * 60)
            print("CONTEXT DETECTION PREFERENCES")
            print("=" * 60)
            print(f"Enabled: {'Yes' if detector.prefs.enabled else 'No'}")
            print(f"Auto-switch: {'Yes' if detector.prefs.auto_switch else 'No (suggest only)'}")
            print(f"Do-not-disturb hours: {', '.join(detector.prefs.do_not_disturb_hours or [])}")
            print(f"Cooldown: {detector.prefs.notification_cooldown_minutes} minutes")
            print(f"Min confidence: {detector.prefs.min_confidence * 100:.0f}%")
            print("=" * 60 + "\n")
            return
        
        # Update preferences
        if args.enabled:
            detector.update_preferences(enabled=True)
            print("✅ Context detection enabled")
        if args.disable:
            detector.update_preferences(enabled=False)
            print("❌ Context detection disabled")
        if args.auto_switch:
            detector.update_preferences(auto_switch=True)
            print("✅ Auto-switch enabled (will switch without asking)")
        if args.no_auto_switch:
            detector.update_preferences(auto_switch=False)
            print("✅ Auto-switch disabled (will suggest only)")
    
    except Exception as e:
        print(f"Error managing context preferences: {e}")
        import traceback
        traceback.print_exc()


def cmd_lora_import(args):
    """Import a community LoRA from HuggingFace (Phase 4 M2)."""  
    if LoRAManager is None:
        print('LoRA manager not available')
        return
    
    try:
        manager = LoRAManager()
        
        print(f"\nImporting LoRA '{args.lora_key}'...")
        print(f"   Source: {args.source}")
        print(f"   Persona: {args.persona}")
        print(f"   Description: {args.description}")
        
        success = manager.import_lora(
            lora_key=args.lora_key,
            source=args.source,
            persona=args.persona,
            description=args.description
        )
        
        if success:
            print(f"\n✅ LoRA '{args.lora_key}' imported to catalog")
            print(f"   Category: community")
            print(f"   Use 'lora-set --lora-key {args.lora_key} --persona {args.persona}' to enable")
            print()
        else:
            print(f"\n⚠ LoRA '{args.lora_key}' already exists in catalog")
    
    except ValueError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"Error importing LoRA: {e}")
        import traceback
        traceback.print_exc()


def cmd_memory_export(args):
    """Export persona memory to file (Phase 4 M1)."""
    if MemoryPurge is None:
        print('memory export not available')
        return
    
    try:
        from pathlib import Path
        
        purge = MemoryPurge()
        output_path = Path(args.output)
        
        # Export to JSONL
        export_file = purge.export_to_jsonl(args.persona, output_path)
        
        print(f"\n✅ Exported {args.persona} memory to: {export_file}")
        print(f"   Size: {output_path.stat().st_size / (1024*1024):.2f} MB")
        print()
    
    except ValueError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"Error exporting memory: {e}")
        import traceback
        traceback.print_exc()


def cmd_model_list(args):
    """List available models across all providers (Phase 5 M1)."""
    if ModelRouter is None:
        print('Model router not available')
        return
    
    try:
        router = ModelRouter()
        models = router.list_available_models()
        
        if not models:
            print("\n⚠ No models available")
            print("   Install Ollama and pull a model:")
            print("   $ ollama pull llama3.1:8b-instruct")
            print()
            return
        
        print("\n" + "=" * 70)
        print("AVAILABLE MODELS")
        print("=" * 70)
        
        # Group by provider
        by_provider = {}
        for model in models:
            provider = model.provider
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append(model)
        
        for provider, provider_models in by_provider.items():
            print(f"\n[{provider.upper()}]")
            for model in provider_models:
                print(f"\n  {model.model_id}")
                print(f"    Memory: ~{model.memory_mb}MB")
                print(f"    Context: {model.context_length:,} tokens")
                print(f"    Capabilities: {', '.join(c.value for c in model.capabilities)}")
                if model.quantization:
                    print(f"    Quantization: {model.quantization}")
        
        print("\n" + "=" * 70 + "\n")
    
    except Exception as e:
        print(f"Error listing models: {e}")
        import traceback
        traceback.print_exc()


def cmd_model_status(args):
    """Show current model router status (Phase 5 M1)."""
    if ModelRouter is None:
        print('Model router not available')
        return
    
    try:
        router = ModelRouter()
        status = router.get_status()
        
        print("\n" + "=" * 70)
        print("MODEL ROUTER STATUS")
        print("=" * 70)
        
        # Orchestrator
        print(f"\nOrchestrator:")
        print(f"  Model: {status['orchestrator']['model_id'] or 'Not configured'}")
        print(f"  Provider: {status['orchestrator']['provider']}")
        print(f"  Loaded: {'Yes' if status['orchestrator']['loaded'] else 'No'}")
        
        # Specialist
        print(f"\nSpecialist:")
        if status['specialist']['enabled']:
            print(f"  Model: {status['specialist']['model_id'] or 'Not configured'}")
            print(f"  Provider: {status['specialist']['provider']}")
            print(f"  Loaded: {'Yes' if status['specialist']['loaded'] else 'No'}")
        else:
            print(f"  Disabled (orchestrator-only mode)")
        
        # Providers
        print(f"\nProviders:")
        for name, healthy in status['providers'].items():
            status_icon = "✅" if healthy else "❌"
            print(f"  {status_icon} {name}")
        
        print("\n" + "=" * 70 + "\n")
    
    except Exception as e:
        print(f"Error getting model status: {e}")
        import traceback
        traceback.print_exc()


def cmd_model_select(args):
    """Select a specialist model (Phase 5 M1)."""
    if ModelRouter is None:
        print('Model router not available')
        return
    
    try:
        router = ModelRouter()
        
        print(f"\nSetting specialist model to: {args.model}")
        print(f"Provider: {args.provider}")
        
        # Update specialist
        router.set_specialist(args.model, args.provider)
        
        print(f"\n✅ Specialist model updated")
        print(f"   Model: {args.model}")
        print(f"   Provider: {args.provider}")
        print(f"\n   The specialist will be loaded on-demand for:")
        print(f"   - Code generation")
        print(f"   - Code analysis")
        print(f"   - Complex reasoning tasks")
        print()
    
    except Exception as e:
        print(f"Error selecting model: {e}")
        import traceback
        traceback.print_exc()


def cmd_model_disable_specialist(args):
    """Disable specialist model (orchestrator-only mode) (Phase 5 M1)."""
    if ModelRouter is None:
        print('Model router not available')
        return
    
    try:
        router = ModelRouter()
        router.disable_specialist()
        
        print("\n✅ Specialist disabled")
        print("   Running in orchestrator-only mode")
        print("   All tasks will use the orchestrator model")
        print()
    
    except Exception as e:
        print(f"Error disabling specialist: {e}")
        import traceback
        traceback.print_exc()


def cmd_hardware_detect(args):
    """Detect hardware and show capabilities (Phase 5 M3)."""
    if HardwareDetector is None:
        print('Hardware detector not available')
        return
    
    try:
        detector = HardwareDetector()
        hardware = detector.detect()
        
        print("\n" + "=" * 70)
        print("HARDWARE DETECTION")
        print("=" * 70)
        print()
        
        print(f"Platform: {hardware.platform_friendly}")
        print(f"Profile: {hardware.profile.value}")
        print()
        
        print("Resources:")
        print(f"  Total RAM: {hardware.total_ram_gb}GB")
        print(f"  Available RAM: {hardware.available_ram_gb:.1f}GB")
        print(f"  CPU Cores: {hardware.cpu_count}")
        
        if hardware.is_apple_silicon:
            print(f"  Apple Silicon: Yes")
            print(f"  Unified Memory: {hardware.unified_memory_gb}GB")
        
        if hardware.has_nvidia_gpu:
            gpu_mem = f" ({hardware.gpu_memory_gb}GB VRAM)" if hardware.gpu_memory_gb else ""
            print(f"  NVIDIA GPU: Yes{gpu_mem}")
        
        if hardware.has_amd_gpu:
            print(f"  AMD GPU: Yes")
        
        print("\n" + "=" * 70 + "\n")
        
        # Show recommendation if requested
        if args.recommend:
            recommendation = detector.recommend_models(hardware)
            
            print("RECOMMENDED CONFIGURATION:")
            print()
            print(f"Orchestrator: {recommendation.orchestrator_model}")
            print(f"  Provider: {recommendation.orchestrator_provider}")
            
            if recommendation.specialist_enabled:
                print(f"Specialist: {recommendation.specialist_model}")
                print(f"  Provider: {recommendation.specialist_provider}")
            else:
                print(f"Specialist: Disabled (orchestrator-only)")
            
            print()
            print(f"Expected Memory: {recommendation.expected_memory_mb}MB")
            print()
            print(f"Reasoning: {recommendation.reasoning}")
            
            if recommendation.performance_notes:
                print()
                print("Performance Notes:")
                for note in recommendation.performance_notes:
                    print(f"  • {note}")
            
            print()
    
    except Exception as e:
        print(f"Error detecting hardware: {e}")
        import traceback
        traceback.print_exc()


def cmd_config_wizard_run(args):
    """Run configuration wizard (Phase 5 M3)."""
    if ConfigWizard is None:
        print('Configuration wizard not available')
        return
    
    try:
        wizard = ConfigWizard()
        
        # Auto or interactive mode
        if args.auto:
            print("Running automatic configuration...")
            config = wizard.run_auto()
        else:
            config = wizard.run_interactive()
        
        if not config:
            return
        
        # Save configuration
        config_path = wizard.save_config(config)
        print(f"\n📄 Configuration saved to: {config_path}")
        
        # Show installation instructions if requested
        if args.install_help:
            hardware = wizard.detect_hardware()
            recommendation = wizard.get_recommendation(hardware)
            wizard.show_installation_instructions(recommendation)
    
    except Exception as e:
        print(f"Error running configuration wizard: {e}")
        import traceback
        traceback.print_exc()


def cmd_config_validate(args):
    """Validate model configuration (Phase 5 M3)."""
    if ConfigWizard is None:
        print('Configuration wizard not available')
        return
    
    try:
        wizard = ConfigWizard()
        
        if wizard.validate_config():
            print("\n✅ Configuration is valid")
        else:
            print("\n❌ Configuration validation failed")
            print("   Run 'cerebric config-wizard' to fix")
    
    except Exception as e:
        print(f"Error validating configuration: {e}")
        import traceback
        traceback.print_exc()


def cmd_mlx_train_lora(args):
    """Train a LoRA adapter for a persona (Phase 5 M4)."""
    try:
        from cerebric_core.cerebric_core.model.persona_lora import PersonaLoRAManager
        from cerebric_core.cerebric_core.persona import PersonaManager
        
        # Initialize managers
        persona_mgr = PersonaManager()
        router = ModelRouter()
        lora_mgr = PersonaLoRAManager(persona_mgr, router)
        
        print(f"\n🎓 Training LoRA for persona: {args.persona}")
        print(f"   Training data: {args.data}")
        print(f"   Model type: {args.model_type}")
        print()
        
        # Training parameters
        kwargs = {
            "rank": args.rank,
            "alpha": args.alpha,
            "epochs": args.epochs,
            "use_qlora": args.qlora,
        }
        
        print("Training parameters:")
        print(f"  Rank: {args.rank}")
        print(f"  Alpha: {args.alpha}")
        print(f"  Epochs: {args.epochs}")
        print(f"  QLoRA: {args.qlora}")
        print()
        
        print("⏳ Training in progress (this may take 2-4 hours)...")
        print("   Optimized for Mac Apple Silicon (128GB unified memory)")
        print()
        
        success = lora_mgr.train_persona_lora(
            persona_name=args.persona,
            training_data_path=args.data,
            model_type=args.model_type,
            **kwargs
        )
        
        if success:
            print("\n✅ LoRA training complete!")
            print(f"   Persona: {args.persona}")
            print(f"   Model type: {args.model_type}")
            print()
            print("💡 Next steps:")
            print(f"   1. Load LoRA: cerebric mlx-load-lora --persona {args.persona}")
            print(f"   2. Test generation with persona-specific LoRA")
        else:
            print("\n❌ LoRA training failed")
    
    except Exception as e:
        print(f"Error training LoRA: {e}")
        import traceback
        traceback.print_exc()


def cmd_mlx_load_lora(args):
    """Load a LoRA adapter for active persona (Phase 5 M4)."""
    try:
        from cerebric_core.cerebric_core.model.persona_lora import PersonaLoRAManager
        from cerebric_core.cerebric_core.persona import PersonaManager
        
        persona_mgr = PersonaManager()
        router = ModelRouter()
        lora_mgr = PersonaLoRAManager(persona_mgr, router)
        
        persona = args.persona or persona_mgr.current_persona
        
        print(f"\n🔄 Loading LoRA for persona: {persona}")
        print(f"   Model type: {args.model_type}")
        
        import time
        start_time = time.time()
        
        success = lora_mgr.load_persona_lora(persona, args.model_type)
        
        load_time = time.time() - start_time
        
        if success:
            print(f"\n✅ LoRA loaded in {load_time:.3f}s")
            print(f"   Persona: {persona}")
            print(f"   Model type: {args.model_type}")
            
            if load_time > 2.0:
                print(f"\n⚠️  Load time ({load_time:.3f}s) exceeds 2s target")
        else:
            print(f"\n❌ Failed to load LoRA for persona '{persona}'")
            print(f"   No LoRA found for {args.model_type} model")
    
    except Exception as e:
        print(f"Error loading LoRA: {e}")
        import traceback
        traceback.print_exc()


def cmd_mlx_lora_status(args):
    """Show LoRA status and available adapters (Phase 5 M4)."""
    try:
        from cerebric_core.cerebric_core.model.persona_lora import PersonaLoRAManager
        from cerebric_core.cerebric_core.persona import PersonaManager
        
        persona_mgr = PersonaManager()
        router = ModelRouter()
        lora_mgr = PersonaLoRAManager(persona_mgr, router)
        
        status = lora_mgr.get_status()
        
        print("\n" + "=" * 70)
        print("LORA STATUS")
        print("=" * 70)
        print()
        
        print(f"Current Persona: {status['current_persona']}")
        print(f"LoRA Directory: {status['lora_dir']}")
        print()
        
        print("Active LoRAs:")
        if status['active_loras']:
            for model_id, persona in status['active_loras'].items():
                print(f"  • {model_id}: {persona}")
        else:
            print("  (none)")
        print()
        
        print("Available LoRAs:")
        available = status['available_loras']
        if available:
            for persona, loras in available.items():
                orch = "✅" if loras['orchestrator'] else "❌"
                spec = "✅" if loras['specialist'] else "❌"
                print(f"  {persona}:")
                print(f"    Orchestrator: {orch}")
                print(f"    Specialist: {spec}")
        else:
            print("  (none)")
        
        print("\n" + "=" * 70 + "\n")
    
    except Exception as e:
        print(f"Error getting LoRA status: {e}")
        import traceback
        traceback.print_exc()


def cmd_mlx_prepare_training_data(args):
    """Prepare training data for a persona (Phase 5 M4)."""
    try:
        from cerebric_core.cerebric_core.model.training_data import (
            prepare_persona_training_data,
            PersonaTrainingDataGenerator,
            validate_training_data
        )
        
        if args.list_personas:
            generator = PersonaTrainingDataGenerator()
            personas = generator.list_available_personas()
            
            print("\n📋 Available persona templates:")
            for p in personas:
                print(f"  • {p}")
            print()
            return
        
        if args.validate:
            print(f"\n🔍 Validating training data: {args.validate}")
            result = validate_training_data(args.validate)
            
            if result['valid']:
                print(f"\n✅ Training data is valid")
                print(f"   Samples: {result['sample_count']}")
                print(f"   File size: {result['file_size_mb']:.2f}MB")
            else:
                print(f"\n❌ Training data validation failed")
                print(f"\nErrors:")
                for error in result['errors']:
                    print(f"  • {error}")
            print()
            return
        
        # Prepare training data
        print(f"\n📝 Preparing training data for persona: {args.persona}")
        print(f"   Output: {args.output}")
        print(f"   Synthetic samples: {args.num_synthetic}")
        print()
        
        count = prepare_persona_training_data(
            persona_name=args.persona,
            output_path=args.output,
            num_synthetic=args.num_synthetic
        )
        
        print(f"\n✅ Training data prepared")
        print(f"   Total samples: {count}")
        print(f"   Saved to: {args.output}")
        print()
        print("💡 Next steps:")
        print(f"   1. Review/edit: {args.output}")
        print(f"   2. Train LoRA: cerebric mlx-train-lora --persona {args.persona} --data {args.output}")
    
    except Exception as e:
        print(f"Error preparing training data: {e}")
        import traceback
        traceback.print_exc()


def cmd_performance_status(args):
    """Show model performance status (Phase 5 M5)."""
    try:
        router = ModelRouter()
        status = router.performance_monitor.get_status()
        
        print("\n" + "=" * 70)
        print("MODEL PERFORMANCE STATUS")
        print("=" * 70)
        print()
        
        # Show per-model metrics
        print("Model Metrics:")
        if status["models"]:
            for model_id, metrics in status["models"].items():
                perf_level = metrics["performance_level"]
                perf_icon = {
                    "excellent": "🟢",
                    "good": "🟡",
                    "acceptable": "🟠",
                    "degraded": "🔴",
                    "critical": "⚫"
                }.get(perf_level, "❓")
                
                print(f"\n  {perf_icon} {model_id} ({metrics['provider']})")
                print(f"     Performance: {perf_level}")
                print(f"     Avg Latency: {metrics['avg_latency_ms']}ms")
                print(f"     P95 Latency: {metrics['p95_latency_ms']}ms")
                print(f"     Error Rate: {metrics['error_rate']:.1%}")
                if metrics['avg_quality'] > 0:
                    print(f"     Avg Quality: {metrics['avg_quality']:.1%}")
                print(f"     Total Requests: {metrics['total_requests']}")
                if metrics['avg_memory_mb'] > 0:
                    print(f"     Avg Memory: {metrics['avg_memory_mb']}MB")
        else:
            print("  (no metrics yet)")
        
        # Show alerts
        print(f"\n\nAlerts (last hour):")
        alerts = status["alerts"]
        if alerts["total"] > 0:
            if alerts["critical"] > 0:
                print(f"  ⚫ Critical: {alerts['critical']}")
            if alerts["error"] > 0:
                print(f"  🔴 Error: {alerts['error']}")
            if alerts["warning"] > 0:
                print(f"  🟡 Warning: {alerts['warning']}")
            if alerts["info"] > 0:
                print(f"  ℹ️  Info: {alerts['info']}")
        else:
            print("  (none)")
        
        # Show recommendations
        if status["recommendations"]:
            print(f"\n\nRecommendations:")
            for rec in status["recommendations"]:
                priority_icon = "🔴" if rec["priority"] == "high" else "🟡"
                print(f"  {priority_icon} {rec['model']}: {rec['message']}")
                print(f"     → {rec['action']}")
        
        print("\n" + "=" * 70 + "\n")
    
    except Exception as e:
        print(f"Error getting performance status: {e}")
        import traceback
        traceback.print_exc()


def cmd_performance_alerts(args):
    """Show performance alerts (Phase 5 M5)."""
    try:
        from cerebric_core.cerebric_core.model.performance_monitor import AlertSeverity
        from datetime import datetime, timedelta
        
        router = ModelRouter()
        
        # Get alerts
        severity = None
        if args.severity:
            severity = AlertSeverity(args.severity)
        
        since = None
        if args.hours:
            since = datetime.now() - timedelta(hours=args.hours)
        
        alerts = router.performance_monitor.get_alerts(severity=severity, since=since)
        
        print("\n" + "=" * 70)
        print("PERFORMANCE ALERTS")
        print("=" * 70)
        print()
        
        if alerts:
            for alert in alerts:
                severity_icon = {
                    "critical": "⚫",
                    "error": "🔴",
                    "warning": "🟡",
                    "info": "ℹ️"
                }.get(alert.severity.value, "❓")
                
                print(f"{severity_icon} [{alert.severity.value.upper()}] {alert.message}")
                print(f"   Metric: {alert.metric}")
                print(f"   Value: {alert.value:.2f} (threshold: {alert.threshold})")
                if alert.model_id:
                    print(f"   Model: {alert.model_id}")
                if alert.recommendation:
                    print(f"   💡 {alert.recommendation}")
                print(f"   Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                print()
        else:
            print("No alerts found.\n")
        
        print("=" * 70 + "\n")
    
    except Exception as e:
        print(f"Error getting alerts: {e}")
        import traceback
        traceback.print_exc()


def cmd_performance_reset(args):
    """Reset performance metrics (Phase 5 M5)."""
    try:
        router = ModelRouter()
        
        if args.model:
            router.performance_monitor.reset_metrics(args.model)
            print(f"\n✅ Reset metrics for: {args.model}\n")
        else:
            router.performance_monitor.reset_metrics()
            print(f"\n✅ Reset all performance metrics\n")
    
    except Exception as e:
        print(f"Error resetting metrics: {e}")
        import traceback
        traceback.print_exc()


def cmd_autonomous_run(args):
    """Run an autonomous task with LLM decision making (Phase 3 M3)."""
    if create_autonomous_task is None:
        print('autonomous tasks not available')
        return
    
    try:
        import json as _json
        
        # Initialize components
        model_mgr = None
        prompt_mgr = None
        mem_retrieval = None
        mem_writer = None
        
        # Try to initialize LLM (optional)
        if ModelManager is not None:
            try:
                model_mgr = ModelManager()
                print(f"✓ LLM loaded: {model_mgr.config.model_id}")
            except Exception as e:
                print(f"⚠ LLM not available: {e}")
                print("  (Task will run without LLM decision making)")
        
        if PromptManager is not None:
            prompt_mgr = PromptManager()
        
        if MemoryRetrieval is not None:
            mem_retrieval = MemoryRetrieval()
        
        if MemoryWriter is not None:
            mem_writer = MemoryWriter()
        
        # Initialize approval engine
        approval_engine = None
        if ApprovalEngine is not None and not args.no_approval:
            approval_engine = ApprovalEngine()
        
        # Create task
        task = create_autonomous_task(
            task_type=args.task_type,
            model_manager=model_mgr,
            prompt_manager=prompt_mgr,
            memory_retrieval=mem_retrieval,
            memory_writer=mem_writer,
            confidence_threshold=args.confidence or 0.7,
            approval_engine=approval_engine
        )
        
        print(f"\n🤖 Executing autonomous task: {args.task_type}")
        print(f"   Confidence threshold: {args.confidence or 0.7}")
        print(f"   LLM enabled: {'Yes' if model_mgr else 'No'}")
        print()
        
        # Parse context if provided
        context = {}
        if args.context:
            context = _json.loads(args.context)
        
        # Execute task
        result = task.execute(context)
        
        # Display result
        print("=" * 60)
        print("TASK RESULT")
        print("=" * 60)
        print(f"Success: {result.get('success', False)}")
        print()
        
        if 'decision' in result:
            decision = result['decision']
            print("LLM DECISION:")
            print(f"  Action: {decision.get('action', 'N/A')}")
            print(f"  Confidence: {decision.get('confidence', 0.0):.2f}")
            print(f"  Reasoning: {decision.get('reasoning', 'N/A')}")
            print(f"  Requires Approval: {decision.get('requires_approval', True)}")
            if decision.get('approval_reason'):
                print(f"  Approval Reason: {decision['approval_reason']}")
            print(f"  Risk Level: {decision.get('risk_level', 'unknown')}")
            print()
        
        if 'state' in result:
            print("SYSTEM STATE:")
            print(_json.dumps(result['state'], indent=2))
            print()
        
        if 'analysis' in result:
            print("ANALYSIS:")
            print(_json.dumps(result['analysis'], indent=2))
            print()
        
        if result.get('requires_approval'):
            print("⚠ This action requires user approval before execution.")
        else:
            print("✓ This action can proceed autonomously (within policy bounds).")
        
        print("=" * 60)
    
    except Exception as e:
        print(f"Error running autonomous task: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description='Cerebric CLI')
    sub = parser.add_subparsers(required=True)

    p_info = sub.add_parser('info', help='Show product info')
    p_info.set_defaults(func=cmd_info)

    p_rm = sub.add_parser('roadmap', help='Show Phase 1 roadmap (docs/Phase1/ROADMAP.md)')
    p_rm.set_defaults(func=cmd_roadmap)

    p_show = sub.add_parser('show', help='Show a project file (relative to Cerebric/)')
    p_show.add_argument('path', help='Relative path, e.g., planning/phase-1-alpha.md')
    p_show.set_defaults(func=cmd_show)

    p_showdoc = sub.add_parser('show-doc', help='Show a docs file (relative to docs/)')
    p_showdoc.add_argument('path', help='Relative path, e.g., Phase1/ROADMAP.md')
    p_showdoc.set_defaults(func=cmd_showdoc)

    p_ing = sub.add_parser('ingest-journald', help='Run journald follower and write JSONL (uses config/ingestion.yml by default)')
    p_ing.add_argument('--config', help='Path to ingestion.yml')
    p_ing.add_argument('--schema', help='Path to telemetry-event.schema.json')
    p_ing.set_defaults(func=cmd_ingest_journald)

    p_ing_hw = sub.add_parser('ingest-hwmon', help='Poll hwmon temp sensors and write JSONL (uses config/ingestion.yml by default)')
    p_ing_hw.add_argument('--config', help='Path to ingestion.yml')
    def _cmd_ing_hw(args):
        default_cfg = None
        if config_dir is not None:
            cand = os.path.join(config_dir(), 'ingestion.yml')
            if os.path.exists(cand):
                default_cfg = cand
        cfg = args.config or default_cfg or os.path.join(os.path.dirname(ROOT), 'config', 'ingestion.yml')
        if run_hwmon is None:
            print('cerebric_core not available or dependencies missing (pyyaml).')
            return
        run_hwmon(cfg)
    p_ing_hw.set_defaults(func=_cmd_ing_hw)

    p_snap = sub.add_parser('snapshot-configs', help='Snapshot tracked config files (uses config/config-registry.yml by default)')
    p_snap.add_argument('--manifest', help='Path to config-registry.yml')
    p_snap.set_defaults(func=cmd_snapshot_configs)

    p_watch = sub.add_parser('watch-configs', help='Watch tracked config files and snapshot on changes')
    p_watch.add_argument('--manifest', help='Path to config-registry.yml')
    p_watch.add_argument('--interval', default='600', help='Polling interval seconds when watchdog is unavailable (default 600)')
    p_watch.set_defaults(func=cmd_watch_configs)

    p_diff = sub.add_parser('diff-configs', help='Diff latest vs previous config snapshots (or provide --prev/--curr)')
    p_diff.add_argument('--prev', help='Path to previous snapshot JSON')
    p_diff.add_argument('--curr', help='Path to current snapshot JSON')
    p_diff.set_defaults(func=cmd_diff_configs)

    p_dash = sub.add_parser('build-dashboard', help='Build dashboard JSON artifacts under data/dashboard')
    p_dash.set_defaults(func=cmd_build_dashboard)

    p_q = sub.add_parser('index-query', help='Query the vector index (self_knowledge_all)')
    p_q.add_argument('text', help='Query text')
    p_q.add_argument('-k', default='5', help='Top-K')
    p_q.set_defaults(func=cmd_index_query)

    p_eval = sub.add_parser('eval-golden', help='Run the golden task harness (stub)')
    p_eval.set_defaults(func=cmd_eval_golden)

    p_idx_cfg = sub.add_parser('index-configs', help='Index canonical config records into the vector DB')
    p_idx_cfg.set_defaults(func=cmd_index_configs)

    p_tick = sub.add_parser('runtime-tick', help='Run one iteration of the runtime (LangGraph if available, else fallback)')
    p_tick.set_defaults(func=cmd_runtime_tick)

    p_pol = sub.add_parser('policy-show', help='Show the currently loaded policy (from config_dir/policy.yml or defaults)')
    p_pol.set_defaults(func=cmd_policy_show)

    p_pev = sub.add_parser('policy-eval', help='Evaluate policy decision for a tool with inputs JSON file (apply path)')
    p_pev.add_argument('--tool', required=True, help='Tool name (e.g., write_config, schedule_cron)')
    p_pev.add_argument('--inputs', required=True, help='Path to JSON file with tool inputs')
    p_pev.set_defaults(func=cmd_policy_eval)

    p_sched_add = sub.add_parser('scheduler-add', help='Add a job to the scheduler queue (Phase 2)')
    p_sched_add.add_argument('--id', required=True, help='Job ID')
    p_sched_add.add_argument('--task', required=True, help='Task name (e.g., snapshot_configs)')
    p_sched_add.add_argument('--schedule', required=True, help='Cron expression or ISO timestamp')
    p_sched_add.add_argument('--priority', default='5', help='Priority (1=highest, 10=lowest)')
    p_sched_add.add_argument('--inputs', required=True, help='Path to JSON file with task inputs')
    p_sched_add.set_defaults(func=cmd_scheduler_add)

    p_sched_list = sub.add_parser('scheduler-list', help='List scheduler jobs (Phase 2)')
    p_sched_list.add_argument('--state', help='Filter by state (pending, running, completed, failed, cancelled)')
    p_sched_list.set_defaults(func=cmd_scheduler_list)

    p_sched_cancel = sub.add_parser('scheduler-cancel', help='Cancel a pending job (Phase 2)')
    p_sched_cancel.add_argument('--id', required=True, help='Job ID')
    p_sched_cancel.set_defaults(func=cmd_scheduler_cancel)

    # Phase 3: Model management commands
    p_model_status = sub.add_parser('model-status', help='Show model status (Phase 3)')
    p_model_status.set_defaults(func=cmd_model_status)

    p_model_test = sub.add_parser('model-test', help='Test model with a prompt (Phase 3)')
    p_model_test.add_argument('--prompt', required=True, help='Test prompt')
    p_model_test.add_argument('--max-tokens', type=int, help='Max tokens to generate')
    p_model_test.set_defaults(func=cmd_model_test)

    p_prompt_show = sub.add_parser('prompt-show', help='Show system prompt for a mode (Phase 3)')
    p_prompt_show.add_argument('--mode', default='interactive', help='Prompt mode (interactive, autonomous, it_admin, friend, custom)')
    p_prompt_show.add_argument('--context', help='Additional task context')
    p_prompt_show.set_defaults(func=cmd_prompt_show)

    p_prompt_init = sub.add_parser('prompt-init', help='Initialize default prompt configuration (Phase 3)')
    p_prompt_init.set_defaults(func=cmd_prompt_init)

    # Phase 3: Memory management commands
    p_mem_query = sub.add_parser('memory-query', help='Query memory (Phase 3)')
    p_mem_query.add_argument('--subdir', required=True, help='Memory subdirectory (core, runtime, personas/friend)')
    p_mem_query.add_argument('--query', required=True, help='Search query')
    p_mem_query.add_argument('--limit', type=int, help='Max results (default: 5)')
    p_mem_query.add_argument('--json', action='store_true', help='Output full JSON')
    p_mem_query.set_defaults(func=cmd_memory_query)

    p_mem_stats = sub.add_parser('memory-stats', help='Show memory statistics (Phase 3)')
    p_mem_stats.set_defaults(func=cmd_memory_stats)

    p_mem_write = sub.add_parser('memory-write', help='Write test entry to memory (Phase 3)')
    p_mem_write.add_argument('--subdir', required=True, help='Memory subdirectory (core, runtime)')
    p_mem_write.add_argument('--entry', required=True, help='JSON entry to write')
    p_mem_write.set_defaults(func=cmd_memory_write)

    # Phase 3: Autonomous executor commands (M3)
    p_exec_status = sub.add_parser('executor-status', help='Show autonomous executor status (Phase 3 M3)')
    p_exec_status.set_defaults(func=cmd_executor_status)

    p_exec_schedule = sub.add_parser('executor-schedule', help='Schedule a cron job (Phase 3 M3)')
    p_exec_schedule.add_argument('--job-id', required=True, help='Unique job identifier')
    p_exec_schedule.add_argument('--cron', required=True, help='Cron expression JSON (e.g., \'{"hour": 2, "minute": 0}\')')
    p_exec_schedule.add_argument('--description', help='Job description')
    p_exec_schedule.add_argument('--daemon', action='store_true', help='Run in daemon mode (keep running)')
    p_exec_schedule.set_defaults(func=cmd_executor_schedule)

    p_exec_list = sub.add_parser('executor-list', help='List scheduled jobs (Phase 3 M3)')
    p_exec_list.set_defaults(func=cmd_executor_list)

    p_exec_cancel = sub.add_parser('executor-cancel', help='Cancel a scheduled job (Phase 3 M3)')
    p_exec_cancel.add_argument('--job-id', required=True, help='Job ID to cancel')
    p_exec_cancel.set_defaults(func=cmd_executor_cancel)

    # Phase 3: Autonomous task execution (M3 - LLM integration demo)
    p_auto_run = sub.add_parser('autonomous-run', help='Run an autonomous task with LLM decision making (Phase 3 M3)')
    p_auto_run.add_argument('--task-type', required=True, choices=['health_check', 'log_cleanup'], help='Type of autonomous task')
    p_auto_run.add_argument('--confidence', type=float, help='Confidence threshold (default: 0.7)')
    p_auto_run.add_argument('--context', help='Task context as JSON string')
    p_auto_run.add_argument('--no-approval', action='store_true', help='Skip approval prompts (auto-approve)')
    p_auto_run.set_defaults(func=cmd_autonomous_run)

    # Phase 3: Approval management (M4)
    p_approval_list = sub.add_parser('approval-list', help='List pending approval requests (Phase 3 M4)')
    p_approval_list.set_defaults(func=cmd_approval_list)

    p_approval_history = sub.add_parser('approval-history', help='Show approval history (Phase 3 M4)')
    p_approval_history.add_argument('--limit', type=int, default=10, help='Max records to show')
    p_approval_history.add_argument('--approved-only', action='store_true', help='Only show approved requests')
    p_approval_history.set_defaults(func=cmd_approval_history)

    # Phase 3: Dashboard (M5)
    p_dashboard = sub.add_parser('dashboard', help='Start Cerebric web dashboard (Phase 3 M5)')
    p_dashboard.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    p_dashboard.add_argument('--port', type=int, default=8000, help='Port to bind to')
    p_dashboard.set_defaults(func=cmd_dashboard_serve)

    # Phase 3: Autonomy Guardrails (M6)
    p_autonomy_status = sub.add_parser('autonomy-status', help='Show autonomy guardrail status (Phase 3 M6)')
    p_autonomy_status.set_defaults(func=cmd_autonomy_status)

    p_autonomy_pause = sub.add_parser('autonomy-pause', help='Pause autonomous operations (safe-mode) (Phase 3 M6)')
    p_autonomy_pause.add_argument('--reason', required=True, help='Reason for pausing autonomy')
    p_autonomy_pause.set_defaults(func=cmd_autonomy_pause)

    p_autonomy_resume = sub.add_parser('autonomy-resume', help='Resume autonomous operations (Phase 3 M6)')
    p_autonomy_resume.add_argument('--user', required=True, help='Your username (for audit trail)')
    p_autonomy_resume.set_defaults(func=cmd_autonomy_resume)

    p_autonomy_anomalies = sub.add_parser('autonomy-anomalies', help='View detected anomalies (Phase 3 M6)')
    p_autonomy_anomalies.add_argument('--hours', type=int, default=24, help='Look back hours (default: 24)')
    p_autonomy_anomalies.set_defaults(func=cmd_autonomy_anomalies)

    p_autonomy_recovery = sub.add_parser('autonomy-recovery', help='View recovery action history (Phase 3 M6)')
    p_autonomy_recovery.add_argument('--limit', type=int, default=20, help='Max records to show (default: 20)')
    p_autonomy_recovery.set_defaults(func=cmd_autonomy_recovery)

    # Phase 4: Persona Management (M1)
    p_persona_list = sub.add_parser('persona-list', help='List available personas (Phase 4 M1)')
    p_persona_list.set_defaults(func=cmd_persona_list)

    p_persona_status = sub.add_parser('persona-status', help='Show active persona status (Phase 4 M1)')
    p_persona_status.set_defaults(func=cmd_persona_status)

    p_persona_switch = sub.add_parser('persona-switch', help='Switch to a different persona (Phase 4 M1)')
    p_persona_switch.add_argument('--to', required=True, choices=['it_admin', 'friend', 'custom'], help='Target persona')
    p_persona_switch.add_argument('--user', help='Your username (for audit trail)')
    p_persona_switch.add_argument('--confirm', action='store_true', help='Confirm the switch (required to execute)')
    p_persona_switch.set_defaults(func=cmd_persona_switch)

    p_memory_purge = sub.add_parser('memory-purge', help='Purge persona-specific memory (Phase 4 M1)')
    p_memory_purge.add_argument('--persona', required=True, help='Persona to purge (e.g., friend, custom)')
    p_memory_purge.add_argument('--user', help='Your username (for audit trail)')
    p_memory_purge.add_argument('--confirm', action='store_true', help='Confirm the purge (required to execute)')
    p_memory_purge.add_argument('--no-export', action='store_true', help='Skip export before purge (not recommended)')
    p_memory_purge.set_defaults(func=cmd_memory_purge)

    p_memory_export = sub.add_parser('memory-export', help='Export persona memory to file (Phase 4 M1)')
    p_memory_export.add_argument('--persona', required=True, help='Persona to export (e.g., friend, custom)')
    p_memory_export.add_argument('--output', required=True, help='Output JSONL file path')
    p_memory_export.set_defaults(func=cmd_memory_export)

    # Phase 4: LoRA Management (M2)
    p_lora_list = sub.add_parser('lora-list', help='List available LoRA adapters (Phase 4 M2)')
    p_lora_list.add_argument('--category', choices=['verified', 'experimental', 'community'], help='Filter by category')
    p_lora_list.set_defaults(func=cmd_lora_list)

    p_lora_info = sub.add_parser('lora-info', help='Show detailed info for a LoRA (Phase 4 M2)')
    p_lora_info.add_argument('--lora-key', required=True, help='LoRA identifier')
    p_lora_info.set_defaults(func=cmd_lora_info)

    p_lora_set = sub.add_parser('lora-set', help='Set LoRA for a persona (Phase 4 M2)')
    p_lora_set.add_argument('--lora-key', required=True, help='LoRA identifier')
    p_lora_set.add_argument('--persona', required=True, choices=['it_admin', 'friend', 'custom'], help='Target persona')
    p_lora_set.set_defaults(func=cmd_lora_set)

    p_lora_import = sub.add_parser('lora-import', help='Import community LoRA from HuggingFace (Phase 4 M2)')
    p_lora_import.add_argument('--lora-key', required=True, help='Unique identifier for this LoRA')
    p_lora_import.add_argument('--source', required=True, help='Source (e.g., huggingface:username/repo)')
    p_lora_import.add_argument('--persona', required=True, choices=['friend', 'custom'], help='Target persona')
    p_lora_import.add_argument('--description', required=True, help='Description of this LoRA')
    p_lora_import.set_defaults(func=cmd_lora_import)

    # Phase 4: Context Awareness (M4)
    p_context_detect = sub.add_parser('context-detect', help='Detect current user context (Phase 4 M4)')
    p_context_detect.set_defaults(func=cmd_context_detect)

    p_context_prefs = sub.add_parser('context-prefs', help='Show/update context detection preferences (Phase 4 M4)')
    p_context_prefs.add_argument('--enabled', action='store_true', help='Enable context detection')
    p_context_prefs.add_argument('--disable', action='store_true', help='Disable context detection')
    p_context_prefs.add_argument('--auto-switch', action='store_true', help='Enable auto-switching (no confirmation)')
    p_context_prefs.add_argument('--no-auto-switch', action='store_true', help='Disable auto-switching (suggest only)')
    p_context_prefs.set_defaults(func=cmd_context_prefs)

    # Phase 5: Model Router (M1)
    p_model_list_router = sub.add_parser('model-list-all', help='List all available models (Phase 5 M1)')
    p_model_list_router.set_defaults(func=cmd_model_list)

    p_model_status_router = sub.add_parser('model-router-status', help='Show model router status (Phase 5 M1)')
    p_model_status_router.set_defaults(func=cmd_model_status)

    p_model_select_router = sub.add_parser('model-select-specialist', help='Select specialist model (Phase 5 M1)')
    p_model_select_router.add_argument('--model', required=True, help='Model ID (e.g., deepseek-coder:33b)')
    p_model_select_router.add_argument('--provider', default='ollama', help='Provider (ollama, llamacpp, mlx)')
    p_model_select_router.set_defaults(func=cmd_model_select)

    p_model_disable = sub.add_parser('model-disable-specialist', help='Disable specialist (orchestrator-only) (Phase 5 M1)')
    p_model_disable.set_defaults(func=cmd_model_disable_specialist)

    # Phase 5 M3: User Configuration & Hardware Detection
    p_hardware_detect = sub.add_parser('hardware-detect', help='Detect hardware and show capabilities (Phase 5 M3)')
    p_hardware_detect.add_argument('--recommend', action='store_true', help='Show model recommendations')
    p_hardware_detect.set_defaults(func=cmd_hardware_detect)

    p_config_wizard = sub.add_parser('config-wizard', help='Run configuration wizard (Phase 5 M3)')
    p_config_wizard.add_argument('--auto', action='store_true', help='Run automatically without prompts')
    p_config_wizard.add_argument('--install-help', action='store_true', help='Show installation instructions')
    p_config_wizard.set_defaults(func=cmd_config_wizard_run)

    p_config_validate = sub.add_parser('config-validate', help='Validate model configuration (Phase 5 M3)')
    p_config_validate.set_defaults(func=cmd_config_validate)

    # Phase 5 M4: MLX & LoRA Commands
    p_mlx_train = sub.add_parser('mlx-train-lora', help='Train LoRA adapter for persona (Phase 5 M4)')
    p_mlx_train.add_argument('--persona', required=True, help='Persona name (e.g., friend, it_admin)')
    p_mlx_train.add_argument('--data', required=True, help='Training data file (JSONL)')
    p_mlx_train.add_argument('--model-type', default='orchestrator', choices=['orchestrator', 'specialist'], help='Model type to train for')
    p_mlx_train.add_argument('--rank', type=int, default=8, help='LoRA rank (default: 8)')
    p_mlx_train.add_argument('--alpha', type=int, default=16, help='LoRA alpha (default: 16)')
    p_mlx_train.add_argument('--epochs', type=int, default=3, help='Training epochs (default: 3)')
    p_mlx_train.add_argument('--qlora', action='store_true', default=True, help='Use QLoRA (default: True)')
    p_mlx_train.set_defaults(func=cmd_mlx_train_lora)

    p_mlx_load = sub.add_parser('mlx-load-lora', help='Load LoRA adapter (Phase 5 M4)')
    p_mlx_load.add_argument('--persona', help='Persona name (defaults to current)')
    p_mlx_load.add_argument('--model-type', default='orchestrator', choices=['orchestrator', 'specialist'], help='Model type')
    p_mlx_load.set_defaults(func=cmd_mlx_load_lora)

    p_mlx_status = sub.add_parser('mlx-lora-status', help='Show LoRA status (Phase 5 M4)')
    p_mlx_status.set_defaults(func=cmd_mlx_lora_status)

    p_mlx_prepare = sub.add_parser('mlx-prepare-training-data', help='Prepare training data for persona (Phase 5 M4)')
    p_mlx_prepare.add_argument('--persona', help='Persona name')
    p_mlx_prepare.add_argument('--output', help='Output file path (JSONL)')
    p_mlx_prepare.add_argument('--num-synthetic', type=int, default=10, help='Number of synthetic samples (default: 10)')
    p_mlx_prepare.add_argument('--list-personas', action='store_true', help='List available persona templates')
    p_mlx_prepare.add_argument('--validate', help='Validate existing training data file')
    p_mlx_prepare.set_defaults(func=cmd_mlx_prepare_training_data)

    # Phase 5 M5: Performance Monitoring
    p_perf_status = sub.add_parser('performance-status', help='Show model performance metrics (Phase 5 M5)')
    p_perf_status.set_defaults(func=cmd_performance_status)

    p_perf_alerts = sub.add_parser('performance-alerts', help='Show performance alerts (Phase 5 M5)')
    p_perf_alerts.add_argument('--severity', choices=['info', 'warning', 'error', 'critical'], help='Filter by severity')
    p_perf_alerts.add_argument('--hours', type=int, default=24, help='Show alerts from last N hours (default: 24)')
    p_perf_alerts.set_defaults(func=cmd_performance_alerts)

    p_perf_reset = sub.add_parser('performance-reset', help='Reset performance metrics (Phase 5 M5)')
    p_perf_reset.add_argument('--model', help='Reset specific model (or all if not specified)')
    p_perf_reset.set_defaults(func=cmd_performance_reset)

    # Phase 7: RAG commands
    p_ask = sub.add_parser('ask', help='Ask a Linux/DevOps question using RAG + LLM (Phase 7)')
    p_ask.add_argument('question', nargs='*', help='Question to ask (can be multiple words)')
    p_ask.add_argument('--model', default='llama3.2:3b', help='Ollama model to use (default: llama3.2:3b)')
    p_ask.add_argument('--no-llm', action='store_true', help='Just retrieve docs, no LLM generation')
    p_ask.add_argument('--top-k', type=int, default=3, help='Number of documents to retrieve (default: 3)')
    def _cmd_ask(args):
        try:
            from pathlib import Path
            import os
            import logging
            
            # Force CPU for embeddings (GPU may be busy)
            os.environ['CUDA_VISIBLE_DEVICES'] = ''
            
            # Suppress verbose logging for CLI
            logging.getLogger('cerebric').setLevel(logging.WARNING)
            logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
            os.environ['TQDM_DISABLE'] = '1'  # Disable progress bars
            
            from cerebric_core.cerebric_core.rag import RAGPipeline
            from cerebric_core.cerebric_core.rag.llm import OllamaLLM, LLMConfig
            
            question = ' '.join(args.question) if args.question else ''
            if not question:
                print('Usage: cerebric ask "your question here"')
                return
            
            print(f'🔍 Searching for: {question}')
            print('   Loading knowledge base...', end=' ', flush=True)
            
            # Initialize RAG
            data_dir = Path(os.path.join(REPO_ROOT, 'data'))
            pipeline = RAGPipeline(data_dir=data_dir, use_reranking=True, top_k=args.top_k)
            
            # Redirect stderr to suppress tqdm
            import sys
            old_stderr = sys.stderr
            sys.stderr = open('/dev/null', 'w')
            try:
                pipeline.load_and_index_documents()
            finally:
                sys.stderr.close()
                sys.stderr = old_stderr
            print('Done!')
            
            # Retrieve
            docs = pipeline.retrieve(question)
            
            if not docs:
                print('❌ No relevant documentation found.')
                return
            
            print(f'\n📚 Found {len(docs)} relevant docs:')
            for i, doc in enumerate(docs, 1):
                # Show source attribution if available (handle nested metadata)
                meta = doc.get('metadata', {})
                # Check for nested metadata (from pipeline indexing)
                if 'metadata' in meta and isinstance(meta['metadata'], dict):
                    inner_meta = meta['metadata']
                else:
                    inner_meta = meta
                source_url = inner_meta.get('source_url') or inner_meta.get('attribution_url', '')
                trust_tier = inner_meta.get('trust_tier', '')
                
                tier_badge = ''
                if trust_tier == 1:
                    tier_badge = ' 🟢'
                elif trust_tier == 2:
                    tier_badge = ' 🟡'
                elif trust_tier:
                    tier_badge = ' 🟠'
                
                if source_url:
                    # Extract domain from URL
                    from urllib.parse import urlparse
                    domain = urlparse(source_url).netloc
                    print(f'   {i}. {doc["name"]}{tier_badge}')
                    print(f'      └─ {domain} (score: {doc["score"]:.2f})')
                else:
                    print(f'   {i}. {doc["name"]} (score: {doc["score"]:.2f})')
            
            if args.no_llm:
                print('\n📖 Content preview:')
                for doc in docs[:2]:
                    print(f'\n--- {doc["name"]} ---')
                    print(doc['content'][:500])
                return
            
            # Generate with LLM
            print('\n💭 Generating answer...')
            llm = OllamaLLM(config=LLMConfig(model=args.model, temperature=0.3))
            
            if not llm.check_available():
                print('⚠️  Ollama not available. Start with: ollama serve')
                print('    Showing retrieved docs instead.')
                for doc in docs[:2]:
                    print(f'\n--- {doc["name"]} ---')
                    print(doc['content'][:500])
                return
            
            answer = llm.generate_with_context(question, docs)
            print(f'\n✨ Answer:\n{answer}')
            
        except ImportError as e:
            print(f'RAG system not available: {e}')
            print('Install with: pip install sentence-transformers rank-bm25')
        except Exception as e:
            print(f'Error: {e}')
    p_ask.set_defaults(func=_cmd_ask)

    # Phase 10: RAG Management Commands
    p_rag_add = sub.add_parser('rag-add', help='Add URL to RAG corpus (Phase 10)')
    p_rag_add.add_argument('url', help='URL to add')
    p_rag_add.add_argument('--trust', action='store_true', help='Trust unknown source')
    def _cmd_rag_add(args):
        try:
            from cerebric_core.cerebric_core.rag.ingestion import RAGIngestionEngine
            
            print(f'🔍 Analyzing: {args.url}')
            
            engine = RAGIngestionEngine()
            result = engine.add_url(args.url, force_trust=args.trust)
            
            if result.success:
                print(f'✅ Added: {result.title}')
                print(f'   Source: {result.source_name} (Tier {result.trust_tier})')
                print(f'   Documents: {result.doc_count}')
                
                if result.warnings:
                    print(f'   ⚠️ Warnings:')
                    for w in result.warnings:
                        print(f'      - {w}')
                
                print(f'\n💡 Run "cerebric rag-merge" to update the corpus index.')
            else:
                print(f'❌ Failed: {result.error}')
                
                if result.warnings:
                    print(f'   Warnings: {result.warnings}')
                    
        except ImportError as e:
            print(f'Ingestion engine not available: {e}')
        except Exception as e:
            print(f'Error: {e}')
    p_rag_add.set_defaults(func=_cmd_rag_add)

    p_rag_sources = sub.add_parser('rag-sources', help='List RAG sources and trust tiers (Phase 10)')
    def _cmd_rag_sources(args):
        try:
            from cerebric_core.cerebric_core.rag.ingestion import SourceRegistry
            
            registry = SourceRegistry()
            
            print('='*60)
            print('RAG Approved Sources')
            print('='*60)
            
            print('\n🟢 Tier 1 - Official Documentation:')
            for s in registry.tier_1:
                print(f'   {s.pattern:<30} {s.name}')
            
            print('\n🟡 Tier 2 - Community Curated:')
            for s in registry.tier_2:
                print(f'   {s.pattern:<30} {s.name}')
            
            print('\n🟠 Tier 3 - Expert Content (manual curation):')
            for s in registry.tier_3:
                note = ' ⚠️ manual' if s.requires_manual_curation else ''
                print(f'   {s.pattern:<30} {s.name}{note}')
            
            print('\n🔴 Blocked:')
            for b in registry.blocked:
                print(f'   {b["pattern"]:<30} ({b.get("reason", "blocked")})')
                
        except Exception as e:
            print(f'Error: {e}')
    p_rag_sources.set_defaults(func=_cmd_rag_sources)

    p_rag_stats = sub.add_parser('rag-stats', help='Show RAG corpus statistics (Phase 10)')
    def _cmd_rag_stats(args):
        try:
            from pathlib import Path
            import json
            
            data_dir = Path(os.path.join(REPO_ROOT, 'data', 'linux'))
            merged_file = data_dir / 'merged' / 'rag_corpus_merged.jsonl'
            user_file = data_dir / 'user-sources' / 'user_added.jsonl'
            
            print('='*60)
            print('RAG Corpus Statistics')
            print('='*60)
            
            # Count merged docs
            if merged_file.exists():
                with open(merged_file) as f:
                    merged_count = sum(1 for _ in f)
                print(f'\n📚 Merged Corpus: {merged_count:,} documents')
            else:
                print('\n📚 Merged Corpus: Not built yet')
            
            # Count user docs
            if user_file.exists():
                with open(user_file) as f:
                    user_count = sum(1 for _ in f)
                print(f'👤 User Added: {user_count:,} documents')
            else:
                print(f'👤 User Added: 0 documents')
            
            # Count by source directory
            print('\n📁 Sources by directory:')
            for source_dir in sorted(data_dir.glob('*/')):
                if source_dir.name in ('merged', 'user-sources'):
                    continue
                jsonl_files = list(source_dir.glob('*.jsonl'))
                if jsonl_files:
                    count = sum(sum(1 for _ in open(f)) for f in jsonl_files)
                    print(f'   {source_dir.name:<25} {count:>5} docs')
                    
        except Exception as e:
            print(f'Error: {e}')
    p_rag_stats.set_defaults(func=_cmd_rag_stats)

    p_rag_merge = sub.add_parser('rag-merge', help='Rebuild RAG corpus from all sources (Phase 10)')
    def _cmd_rag_merge(args):
        try:
            import subprocess
            merge_script = os.path.join(REPO_ROOT, 'scripts', 'quick_merge_rag.py')
            
            print('🔄 Merging RAG corpus...')
            result = subprocess.run(
                ['python', merge_script],
                cwd=REPO_ROOT,
                capture_output=False
            )
            
            if result.returncode == 0:
                print('\n✅ Corpus merged successfully!')
            else:
                print('\n❌ Merge failed')
                
        except Exception as e:
            print(f'Error: {e}')
    p_rag_merge.set_defaults(func=_cmd_rag_merge)

    p_rag_check = sub.add_parser('rag-check', help='Check URL before adding (Phase 10)')
    p_rag_check.add_argument('url', help='URL to check')
    def _cmd_rag_check(args):
        try:
            from cerebric_core.cerebric_core.rag.ingestion import (
                SourceRegistry, URLAnalyzer, ContentExtractor, QualityValidator
            )
            from urllib.parse import urlparse
            
            print(f'🔍 Checking: {args.url}')
            print('='*60)
            
            # Check source registry
            registry = SourceRegistry()
            source_info, blocked_reason = registry.check_source(args.url)
            
            if blocked_reason:
                print(f'❌ BLOCKED: {blocked_reason}')
                return
            
            if source_info:
                tier_emoji = {1: '🟢', 2: '🟡', 3: '🟠'}.get(source_info.tier, '⚪')
                print(f'{tier_emoji} Source: {source_info.name} (Tier {source_info.tier})')
                if source_info.requires_manual_curation:
                    print('   ⚠️  Requires manual curation')
            else:
                print('⚪ Source: Unknown (not in approved registry)')
                print('   Use --trust flag to add anyway')
            
            # Validate URL
            print('\n📡 Validating URL...')
            analyzer = URLAnalyzer()
            valid, content_type = analyzer.validate_url(args.url)
            
            if not valid:
                print(f'❌ URL Error: {content_type}')
                return
            
            print(f'✅ Accessible: {analyzer.detect_content_type(content_type)}')
            
            if analyzer.check_js_heavy(args.url):
                print('⚠️  May require JavaScript (extraction might be incomplete)')
            
            # Extract content preview
            print('\n📄 Extracting content...')
            extractor = ContentExtractor()
            title, description, content = extractor.extract_html(args.url)
            
            if not content:
                print('❌ Failed to extract content')
                return
            
            print(f'✅ Title: {title}')
            print(f'   Length: {len(content):,} chars')
            
            # Validate quality
            validator = QualityValidator()
            is_valid, warnings = validator.validate(title, content)
            
            if is_valid:
                print('✅ Quality: Passes validation')
            else:
                print(f'❌ Quality: Failed - {warnings}')
            
            for w in warnings:
                print(f'   ⚠️  {w}')
            
            print('\n' + '='*60)
            if is_valid and (source_info or True):  # Can be added
                print('✅ Ready to add: cerebric rag-add ' + args.url)
            else:
                print('❌ Cannot add this URL')
                
        except Exception as e:
            print(f'Error: {e}')
    p_rag_check.set_defaults(func=_cmd_rag_check)

    p_rag_bulk = sub.add_parser('rag-bulk', help='Add multiple URLs from file (Phase 10)')
    p_rag_bulk.add_argument('file', help='File with URLs (one per line)')
    p_rag_bulk.add_argument('--trust', action='store_true', help='Trust unknown sources')
    def _cmd_rag_bulk(args):
        try:
            from cerebric_core.cerebric_core.rag.ingestion import RAGIngestionEngine
            
            # Read URLs from file
            with open(args.file) as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            print(f'📋 Found {len(urls)} URLs in {args.file}')
            print('='*60)
            
            engine = RAGIngestionEngine()
            
            success = 0
            failed = 0
            
            for i, url in enumerate(urls, 1):
                print(f'\n[{i}/{len(urls)}] {url[:60]}...')
                result = engine.add_url(url, force_trust=args.trust)
                
                if result.success:
                    print(f'   ✅ {result.title[:50]}')
                    success += 1
                else:
                    print(f'   ❌ {result.error}')
                    failed += 1
            
            print('\n' + '='*60)
            print(f'✅ Added: {success}')
            print(f'❌ Failed: {failed}')
            
            if success > 0:
                print(f'\n💡 Run "cerebric rag-merge" to update the corpus.')
                
        except FileNotFoundError:
            print(f'❌ File not found: {args.file}')
        except Exception as e:
            print(f'Error: {e}')
    p_rag_bulk.set_defaults(func=_cmd_rag_bulk)

    p_rag_sitemap = sub.add_parser('rag-sitemap', help='Discover URLs from sitemap (Phase 10)')
    p_rag_sitemap.add_argument('sitemap_url', help='Sitemap URL (e.g., https://site.com/sitemap.xml)')
    p_rag_sitemap.add_argument('--include', nargs='*', help='Only include URLs containing these patterns')
    p_rag_sitemap.add_argument('--exclude', nargs='*', help='Exclude URLs containing these patterns')
    p_rag_sitemap.add_argument('--max', type=int, default=50, help='Max URLs to show (default: 50)')
    p_rag_sitemap.add_argument('--add', action='store_true', help='Actually add the URLs (otherwise just preview)')
    p_rag_sitemap.add_argument('--trust', action='store_true', help='Trust unknown sources')
    def _cmd_rag_sitemap(args):
        try:
            from cerebric_core.cerebric_core.rag.ingestion import (
                SitemapCrawler, RAGIngestionEngine, SourceRegistry
            )
            
            print(f'🗺️  Fetching sitemap: {args.sitemap_url}')
            
            crawler = SitemapCrawler()
            urls = crawler.fetch_sitemap(args.sitemap_url)
            
            if not urls:
                print('❌ No URLs found in sitemap')
                return
            
            print(f'   Found {len(urls)} URLs in sitemap')
            
            # Filter
            filtered = crawler.filter_urls(
                urls,
                include_patterns=args.include,
                exclude_patterns=args.exclude,
                max_urls=args.max
            )
            
            print(f'   After filtering: {len(filtered)} URLs')
            print()
            
            # Check source trust
            registry = SourceRegistry()
            source_info, blocked_reason = registry.check_source(filtered[0] if filtered else '')
            
            if blocked_reason:
                print(f'❌ Blocked source: {blocked_reason}')
                return
            
            if source_info:
                tier_emoji = {1: '🟢', 2: '🟡', 3: '🟠'}.get(source_info.tier, '⚪')
                print(f'{tier_emoji} Source: {source_info.name} (Tier {source_info.tier})')
            else:
                print('⚪ Unknown source (use --trust to add)')
                if not args.trust and args.add:
                    print('   Aborting. Use --trust to add unknown sources.')
                    return
            
            print()
            print('URLs to add:')
            for i, url in enumerate(filtered[:20], 1):
                print(f'   {i}. {url}')
            if len(filtered) > 20:
                print(f'   ... and {len(filtered) - 20} more')
            
            if not args.add:
                print()
                print(f'💡 Preview only. Add --add to actually ingest these URLs.')
                return
            
            # Actually add the URLs
            print()
            print('='*60)
            print('Adding URLs...')
            
            engine = RAGIngestionEngine()
            success = 0
            failed = 0
            
            for i, url in enumerate(filtered, 1):
                result = engine.add_url(url, force_trust=args.trust)
                if result.success:
                    print(f'   [{i}/{len(filtered)}] ✅ {result.title[:50]}')
                    success += 1
                else:
                    print(f'   [{i}/{len(filtered)}] ❌ {result.error[:50]}')
                    failed += 1
            
            print()
            print(f'✅ Added: {success}')
            print(f'❌ Failed: {failed}')
            
            if success > 0:
                print(f'\n💡 Run "cerebric rag-merge" to update the corpus.')
                
        except Exception as e:
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()
    p_rag_sitemap.set_defaults(func=_cmd_rag_sitemap)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
