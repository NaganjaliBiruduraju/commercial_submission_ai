"""
Test the Commercial Submission AI API endpoints.
Simple HTTP client tests without authentication.
"""
import httpx
import json

BASE_URL = "http://localhost:8000"


def test_health():
    """Test health endpoint."""
    print("\n=== Testing Health Endpoint ===")
    response = httpx.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_root():
    """Test root endpoint."""
    print("\n=== Testing Root Endpoint ===")
    response = httpx.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_openapi():
    """Test OpenAPI schema."""
    print("\n=== Testing OpenAPI Schema ===")
    response = httpx.get(f"{BASE_URL}/openapi.json")
    print(f"Status: {response.status_code}")
    schema = response.json()
    print(f"API Title: {schema.get('info', {}).get('title')}")
    print(f"API Version: {schema.get('info', {}).get('version')}")
    print(f"Total Endpoints: {len(schema.get('paths', {}))}")
    return response.status_code == 200


def test_docs():
    """Test that docs are accessible."""
    print("\n=== Testing Documentation ===")
    response = httpx.get(f"{BASE_URL}/docs")
    print(f"Status: {response.status_code}")
    print(f"Swagger UI is accessible: {response.status_code == 200}")
    return response.status_code == 200


if __name__ == "__main__":
    print("🚀 Testing Commercial Submission AI API")
    print(f"Base URL: {BASE_URL}")
    
    tests = [
        test_health,
        test_root,
        test_openapi,
        test_docs,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
                print("✅ PASSED")
            else:
                failed += 1
                print("❌ FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ ERROR: {e}")
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Your API is working perfectly.")
        print(f"\n📖 Open the interactive docs: {BASE_URL}/docs")
        print("   You can test all endpoints there with a user-friendly interface.")
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")
