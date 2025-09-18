# test_imports.py
print("Testing NOURA modular imports...")

try:
    from noura_core_v1_3 import NOURA_CORE
    print(f"✅ Core loaded - Version: {NOURA_CORE['version']}")
    
    from noura_templates_v1_3 import TEMPLATES
    print(f"✅ Templates loaded - Languages: {list(TEMPLATES['greeting'].keys())}")
    
    from noura_state_machine_v1_3 import STATE_MACHINE
    print(f"✅ State Machine loaded - States: {list(STATE_MACHINE['states'].keys())}")
    
    from main_v2 import app, NOURASession, NOURAProcessor
    print("✅ Main app loaded successfully")
    
    print("\n🎉 All imports successful! Ready for testing.")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
