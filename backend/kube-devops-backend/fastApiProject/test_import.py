#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

try:
    from routers import tasks_advanced
    print("✅ SUCCESS: tasks_advanced imported successfully")
    print(f"✅ Router prefix: {tasks_advanced.router.prefix}")
    print(f"✅ Router routes: {len(tasks_advanced.router.routes)} routes")
except ImportError as e:
    print(f"❌ IMPORT ERROR: {e}")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
