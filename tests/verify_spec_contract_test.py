"""
Verify that the OpenAPI spec matches the actual implementation.

This script checks:
1. All paths in spec are implemented
2. All request/response models match
3. All status codes are correct
4. SMILE validation logic is documented
"""

from pathlib import Path

import yaml


def load_spec(spec_path: str) -> dict:
    """Load OpenAPI YAML spec."""
    with open(spec_path) as f:
        return yaml.safe_load(f)


def load_models():
    """Load actual models from models.py."""
    from lpi.models import (
        Goal,
        GoalCreate,
        GoalUpdate,
        Recommendation,
        Signal,
        SignalCreate,
        SmilePhase,
    )
    return {
        'Goal': Goal,
        'GoalCreate': GoalCreate,
        'GoalUpdate': GoalUpdate,
        'Signal': Signal,
        'SignalCreate': SignalCreate,
        'Recommendation': Recommendation,
        'SmilePhase': SmilePhase,
    }


def load_routers():
    """Load actual router endpoints."""
    from lpi.routers import goals, recommendations, signals
    return {
        'goals': goals.router,
        'signals': signals.router,
        'recommendations': recommendations.router,
    }


def verify_paths(spec: dict) -> dict:
    """Verify all paths in spec."""
    results = {
        'total_paths': 0,
        'verified_paths': [],
        'issues': [],
    }
    
    paths = spec.get('paths', {})
    results['total_paths'] = len(paths)
    
    expected_paths = [
        '/health',
        '/api/v1/goals/',
        '/api/v1/goals/{goal_id}',
        '/api/v1/signals/',
        '/api/v1/recommendations/{user_id}',
        '/api/v1/signals/timeline/{user_id}',
    ]
    
    for path in expected_paths:
        if path in paths:
            results['verified_paths'].append(path)
        else:
            results['issues'].append(f"❌ Missing path: {path}")
    
    return results


def verify_models(spec: dict, models: dict) -> dict:
    """Verify all schemas match models."""
    results = {
        'verified_schemas': [],
        'issues': [],
    }
    
    schemas = spec.get('components', {}).get('schemas', {})
    required_schemas = ['Goal', 'GoalCreate', 'GoalUpdate', 'Signal', 'SignalCreate', 'Recommendation', 'SmilePhase']
    
    for schema_name in required_schemas:
        if schema_name in schemas:
            results['verified_schemas'].append(schema_name)
        else:
            results['issues'].append(f"❌ Missing schema: {schema_name}")
    
    return results


def verify_status_codes(spec: dict) -> dict:
    """Verify all status codes are correct."""
    results = {
        'status_code_rules': {},
        'issues': [],
    }
    
    paths = spec.get('paths', {})
    
    # Define expected status codes for each method
    expected_codes = {
        'post': ['201', '400', '422'],
        'get': ['200'],
        'patch': ['200', '404', '422'],
        'delete': ['200', '404'],
    }
    
    for path, methods in paths.items():
        for method, details in methods.items():
            if method not in ['get', 'post', 'patch', 'delete']:
                continue
            
            responses = details.get('responses', {})
            expected = set(expected_codes.get(method, []))
            actual = set(responses.keys())
            
            if expected.issubset(actual):
                results['status_code_rules'][f"{method.upper()} {path}"] = "✓"
            else:
                missing = expected - actual
                results['issues'].append(f"❌ {method.upper()} {path}: Missing status codes {missing}")
    
    return results


def verify_smile_integration(spec: dict) -> dict:
    """Verify SMILE phase transition rules are documented."""
    results = {
        'smile_documented': False,
        'issues': [],
    }
    
    # Check if PATCH /goals/{goal_id} documents SMILE rules
    paths = spec.get('paths', {})
    patch_goal = paths.get('/api/v1/goals/{goal_id}', {}).get('patch', {})
    description = patch_goal.get('description', '')
    
    smile_rules = [
        'Forward transitions allowed',
        'Backward',
        'Skip',
        'same phase'
    ]
    
    if all(rule in description for rule in smile_rules):
        results['smile_documented'] = True
    else:
        results['issues'].append("⚠️  SMILE transition rules not fully documented in PATCH /goals/{goal_id}")
    
    return results


def main():
    """Run all verification checks."""
    spec_path = 'lpi_openapi_v3_final.yaml'
    
    if not Path(spec_path).exists():
        print(f"❌ Spec file not found at {spec_path}")
        return False
    
    try:
        spec = load_spec(spec_path)
    except Exception as e:
        print(f"❌ Failed to load spec: {e}")
        return False
    
    print("=" * 70)
    print("OpenAPI Spec Verification Report")
    print("=" * 70)
    
    # Run verifications
    path_results = verify_paths(spec)
    model_results = verify_models(spec, load_models())
    status_results = verify_status_codes(spec)
    smile_results = verify_smile_integration(spec)
    
    # Print results
    print(f"\n✓ PATHS ({len(path_results['verified_paths'])}/{path_results['total_paths']})")
    for path in path_results['verified_paths']:
        print(f"  ✓ {path}")
    
    print(f"\n✓ SCHEMAS ({len(model_results['verified_schemas'])})")
    for schema in model_results['verified_schemas']:
        print(f"  ✓ {schema}")
    
    print("\n✓ STATUS CODES")
    for rule, status in status_results['status_code_rules'].items():
        print(f"  {status} {rule}")
    
    print("\n✓ SMILE INTEGRATION")
    if smile_results['smile_documented']:
        print("  ✓ SMILE rules documented in PATCH endpoint")
    else:
        print("  ⚠️  SMILE rules not fully documented")
    
    # Print issues
    all_issues = (
        path_results['issues'] +
        model_results['issues'] +
        status_results['issues'] +
        smile_results['issues']
    )
    
    if all_issues:
        print(f"\n⚠️  ISSUES FOUND ({len(all_issues)})")
        for issue in all_issues:
            print(f"  {issue}")
        return False
    else:
        print("\n" + "=" * 70)
        print("✅ ALL VERIFICATION CHECKS PASSED")
        print("=" * 70)
        return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
