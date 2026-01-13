#!/usr/bin/env python3
"""
Verification script to test main components of the Python automation implementation.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test that all main modules can be imported."""
    print("Testing imports...")
    try:
        from copilot_agent.app import app, system_status, get_post_pr_status_for_issue
        print("✓ Main app imports successfully")
        
        from copilot_agent.lib.autopilot import Autopilot
        print("✓ Autopilot imports successfully")
        
        from copilot_agent.lib.github import (
            get_latest_workflow_run_for_ref,
            get_jobs_for_run,
            find_copilot_sub_pr,
            merge_pull_request,
            mark_pull_request_ready_for_review,
            approve_pull_request,
            enable_pull_request_auto_merge,
            is_pull_request_merged,
            get_active_org_prs_with_jira_keys
        )
        print("✓ All GitHub functions import successfully")
        
        from copilot_agent.lib.jira import search_issues, get_issue_details
        print("✓ Jira functions import successfully")
        
        from copilot_agent.lib.workflow_factory import generate_workflow, generate_dockerfile
        print("✓ Workflow factory imports successfully")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_system_status():
    """Test system status structure."""
    print("\nTesting system status...")
    try:
        from copilot_agent.app import system_status
        
        required_keys = [
            "activeTickets",
            "monitoredTickets",
            "processedCount",
            "scanHistory",
            "currentPhase",
            "currentTicketKey",
            "currentTicketLogs",
            "currentJiraUrl",
            "currentPrUrl",
            "currentPayload",
            "nextScanTime"
        ]
        
        for key in required_keys:
            if key not in system_status:
                print(f"✗ Missing key in system_status: {key}")
                return False
        
        print(f"✓ System status has all required keys: {len(required_keys)} keys")
        return True
    except Exception as e:
        print(f"✗ System status test failed: {e}")
        return False

def test_config_loading():
    """Test configuration loading."""
    print("\nTesting configuration...")
    try:
        from copilot_agent.app import board_post_pr_status, get_post_pr_status_for_issue
        
        print(f"✓ Board config loaded: {len(board_post_pr_status)} projects")
        
        # Test function
        test_status = get_post_pr_status_for_issue("TEST-123")
        print(f"✓ Status function works: TEST-123 → '{test_status}'")
        
        return True
    except Exception as e:
        print(f"✗ Config test failed: {e}")
        return False

def test_dashboard_files():
    """Test that dashboard files exist."""
    print("\nTesting dashboard files...")
    try:
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        public_dir = project_root / "public"
        
        required_files = ["index.html", "styles.css", "app.js"]
        
        for file in required_files:
            file_path = public_dir / file
            if not file_path.exists():
                print(f"✗ Missing dashboard file: {file}")
                return False
            print(f"✓ Found {file} ({file_path.stat().st_size} bytes)")
        
        return True
    except Exception as e:
        print(f"✗ Dashboard files test failed: {e}")
        return False

def test_dockerfile():
    """Test that Dockerfile exists."""
    print("\nTesting Dockerfile...")
    try:
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        dockerfile = project_root / "Dockerfile"
        
        if not dockerfile.exists():
            print("✗ Dockerfile not found")
            return False
        
        content = dockerfile.read_text()
        if "python" not in content.lower():
            print("✗ Dockerfile doesn't appear to be for Python")
            return False
        
        print(f"✓ Dockerfile exists ({len(content)} bytes)")
        return True
    except Exception as e:
        print(f"✗ Dockerfile test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("JIRA-ACTION Python automation verification")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("System Status", test_system_status),
        ("Configuration", test_config_loading),
        ("Dashboard Files", test_dashboard_files),
        ("Dockerfile", test_dockerfile),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:10} {name}")
    
    print("=" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 All tests passed! The Python automation implementation is ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
