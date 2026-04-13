import requests
import sys
import json
from datetime import datetime

class AskBaseAPITester:
    def __init__(self, base_url="https://ollama-query-engine.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=30):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else f"{self.api_url}/"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, response.text
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "response": response.text[:200]
                })
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e)
            })
            return False, {}

    def test_root_endpoint(self):
        """Test GET /api/ - root endpoint"""
        return self.run_test("Root Endpoint", "GET", "", 200)

    def test_schema_endpoint(self):
        """Test GET /api/schema - returns schema definition and document counts"""
        success, response = self.run_test("Schema Endpoint", "GET", "schema", 200)
        if success and response:
            # Validate schema structure
            if 'schema' in response and 'counts' in response:
                print(f"   Schema collections: {list(response['schema'].keys())}")
                print(f"   Document counts: {response['counts']}")
                return True
            else:
                print(f"❌ Schema response missing required fields")
                return False
        return success

    def test_seed_endpoint(self):
        """Test POST /api/seed - seeds the database"""
        success, response = self.run_test("Seed Database", "POST", "seed", 200, timeout=60)
        if success and response:
            if 'counts' in response:
                print(f"   Seeded counts: {response['counts']}")
                return True
        return success

    def test_stats_endpoint(self):
        """Test GET /api/stats - returns database statistics"""
        success, response = self.run_test("Database Stats", "GET", "stats", 200)
        if success and response:
            if 'counts' in response and 'total' in response:
                print(f"   Stats: {response}")
                return True
        return success

    def test_query_endpoint(self):
        """Test POST /api/query - natural language to MongoDB query"""
        test_questions = [
            "Show me all active users",
            "How many orders are pending?",
            "Find products under $50 sorted by price"
        ]
        
        all_passed = True
        for question in test_questions:
            success, response = self.run_test(
                f"Query: '{question}'", 
                "POST", 
                "query", 
                200, 
                {"question": question},
                timeout=45
            )
            if success and response:
                # Validate query response structure
                required_fields = ['question', 'generated_query', 'results', 'row_count', 'execution_time_ms']
                missing_fields = [field for field in required_fields if field not in response]
                if missing_fields:
                    print(f"❌ Missing fields in response: {missing_fields}")
                    all_passed = False
                else:
                    print(f"   Generated query: {response.get('generated_query', {}).get('collection', 'N/A')}")
                    print(f"   Results count: {response.get('row_count', 0)}")
                    print(f"   Execution time: {response.get('execution_time_ms', 0)}ms")
            else:
                all_passed = False
        
        return all_passed

    def test_history_endpoints(self):
        """Test GET /api/history and DELETE /api/history"""
        # Test getting history
        success1, response = self.run_test("Get History", "GET", "history", 200)
        history_works = success1 and 'history' in response
        
        if history_works:
            print(f"   History items: {len(response['history'])}")
        
        # Test clearing history
        success2, _ = self.run_test("Clear History", "DELETE", "history", 200)
        
        # Test getting history again to verify it's cleared
        success3, response2 = self.run_test("Get History After Clear", "GET", "history", 200)
        cleared_properly = success3 and response2.get('history', []) == []
        
        if not cleared_properly:
            print(f"❌ History not properly cleared")
        
        return history_works and success2 and cleared_properly

def main():
    print("🚀 Starting AskBase API Testing...")
    print("=" * 50)
    
    tester = AskBaseAPITester()
    
    # Test all endpoints in logical order
    tests = [
        ("Root Endpoint", tester.test_root_endpoint),
        ("Schema Endpoint", tester.test_schema_endpoint),
        ("Seed Database", tester.test_seed_endpoint),
        ("Database Stats", tester.test_stats_endpoint),
        ("Query Processing", tester.test_query_endpoint),
        ("History Management", tester.test_history_endpoints),
    ]
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            test_func()
        except Exception as e:
            print(f"❌ Test suite error in {test_name}: {str(e)}")
    
    # Print final results
    print(f"\n{'='*50}")
    print(f"📊 FINAL RESULTS")
    print(f"{'='*50}")
    print(f"Tests passed: {tester.tests_passed}/{tester.tests_run}")
    print(f"Success rate: {(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "No tests run")
    
    if tester.failed_tests:
        print(f"\n❌ FAILED TESTS:")
        for failure in tester.failed_tests:
            print(f"  - {failure}")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())