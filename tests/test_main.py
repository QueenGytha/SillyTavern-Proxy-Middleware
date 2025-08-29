import pytest
import json
from unittest.mock import Mock, patch
from flask import Flask
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the main application
from main import app

class TestMainApplication:
    """Test suite for the main Flask application"""
    
    @pytest.fixture
    def app(self):
        """Create a test Flask application"""
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create a test client"""
        return app.test_client()
    
    @pytest.fixture
    def sample_chat_request(self):
        """Sample OpenAI-compatible chat completion request"""
        return {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": False
        }
    
    @pytest.fixture
    def sample_streaming_request(self):
        """Sample streaming chat completion request"""
        return {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": True
        }

    def test_app_creation(self, app):
        """Test that the Flask app can be created"""
        assert app is not None
        assert app.config['TESTING'] is True

    def test_health_check_endpoint(self, client):
        """Test health check endpoint exists and responds"""
        # This test will fail until we implement the endpoint
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json == {"status": "healthy"}

    def test_models_endpoint_exists(self, client):
        """Test that /models endpoint exists"""
        response = client.get('/models')
        assert response.status_code == 200

    def test_models_endpoint_returns_openai_format(self, client):
        """Test that /models returns OpenAI-compatible format"""
        response = client.get('/models')
        data = response.get_json()
        
        assert 'object' in data
        assert data['object'] == 'list'
        assert 'data' in data
        assert isinstance(data['data'], list)
        
        # Check that each model has required fields
        for model in data['data']:
            assert 'id' in model
            assert 'object' in model
            assert model['object'] == 'model'

    def test_models_endpoint_url_construction(self, client):
        """Test that /models endpoint constructs correct URL for target proxy"""
        with patch('proxy_client.ProxyClient.forward_request') as mock_forward:
            # Mock successful response
            mock_response = {
                "object": "list",
                "data": [
                    {"id": "test-model", "object": "model"}
                ]
            }
            mock_forward.return_value = mock_response
            
            response = client.get('/models')
            
            # Verify the mock was called with correct parameters
            mock_forward.assert_called_once()
            call_args = mock_forward.call_args
            
            # Check that endpoint was passed as empty string
            assert call_args[1]['endpoint'] == ""
            # Check that method was GET
            assert call_args[1]['method'] == "GET"
            # Check that request_data was empty
            assert call_args[1]['request_data'] == {}

    def test_models_endpoint_url_construction_logic(self, client):
        """Test that /models endpoint correctly constructs the models URL from target URL"""
        with patch('config.Config.get_target_proxy_config') as mock_config:
            # Mock the target proxy config
            mock_config.return_value = {
                "url": "https://test-proxy.example.com/proxy/google-ai/chat/completions"
            }
            
            with patch('proxy_client.ProxyClient') as mock_proxy_client_class:
                # Mock the proxy client instance
                mock_proxy_client = Mock()
                mock_proxy_client_class.return_value = mock_proxy_client
                
                # Mock successful response
                mock_proxy_client.forward_request.return_value = {
                    "object": "list",
                    "data": [{"id": "test-model", "object": "model"}]
                }
                
                response = client.get('/models')
                
                # Verify ProxyClient was created with correct models URL
                mock_proxy_client_class.assert_called_once()
                call_args = mock_proxy_client_class.call_args
                models_url = call_args[0][0]  # First positional argument
                
                # Should be the base URL + /models
                expected_url = "https://test-proxy.example.com/proxy/google-ai/models"
                assert models_url == expected_url
                
                # Verify forward_request was called with correct parameters
                mock_proxy_client.forward_request.assert_called_once()
                forward_call_args = mock_proxy_client.forward_request.call_args
                assert forward_call_args[1]['endpoint'] == ""
                assert forward_call_args[1]['method'] == "GET"

    def test_models_endpoint_fallback_to_default_models(self, client):
        """Test that /models falls back to default models when target proxy fails"""
        with patch('proxy_client.ProxyClient.forward_request') as mock_forward:
            # Mock failure
            mock_forward.side_effect = Exception("Target proxy unavailable")
            
            response = client.get('/models')
            data = response.get_json()
            
            # Should return default models
            assert 'object' in data
            assert data['object'] == 'list'
            assert 'data' in data
            assert isinstance(data['data'], list)
            
            # Check that default models are returned
            from constants import DEFAULT_MODELS
            assert data['data'] == DEFAULT_MODELS

    def test_models_endpoint_with_authentication_headers(self, client):
        """Test that /models properly forwards authentication headers"""
        with patch('proxy_client.ProxyClient.forward_request') as mock_forward:
            # Mock successful response
            mock_response = {
                "object": "list",
                "data": [
                    {"id": "test-model", "object": "model"}
                ]
            }
            mock_forward.return_value = mock_response
            
            # Make request with auth header
            headers = {'Authorization': 'Bearer test-token'}
            response = client.get('/models', headers=headers)
            
            # Verify the mock was called with auth header
            mock_forward.assert_called_once()
            call_args = mock_forward.call_args
            forwarded_headers = call_args[1]['headers']
            
            assert 'Authorization' in forwarded_headers
            assert forwarded_headers['Authorization'] == 'Bearer test-token'

    def test_models_endpoint_handles_http_errors(self, client):
        """Test that /models handles HTTP errors from target proxy"""
        with patch('proxy_client.ProxyClient.forward_request') as mock_forward:
            from requests.exceptions import HTTPError
            from requests import Response
            
            # Mock HTTP error response
            mock_response = Response()
            mock_response.status_code = 404
            mock_response._content = b'{"error": "Not found"}'
            mock_forward.side_effect = HTTPError("404 Client Error", response=mock_response)
            
            response = client.get('/models')
            data = response.get_json()
            
            # Should return default models on HTTP error
            assert 'object' in data
            assert data['object'] == 'list'
            assert 'data' in data
            assert isinstance(data['data'], list)
            
            # Check that default models are returned
            from constants import DEFAULT_MODELS
            assert data['data'] == DEFAULT_MODELS

    def test_chat_completions_endpoint_exists(self, client, sample_chat_request):
        """Test that /chat/completions endpoint exists"""
        response = client.post('/chat/completions', 
                             json=sample_chat_request,
                             content_type='application/json')
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404

    def test_chat_completions_accepts_valid_request(self, client, sample_chat_request):
        """Test that /chat/completions accepts valid OpenAI format"""
        response = client.post('/chat/completions', 
                             json=sample_chat_request,
                             content_type='application/json')
        
        # Should return some response (not necessarily 200 if proxy is down)
        assert response.status_code in [200, 502, 503, 504]

    def test_chat_completions_rejects_invalid_request(self, client):
        """Test that /chat/completions rejects invalid requests"""
        invalid_request = {
            "model": "gpt-3.5-turbo",
            # Missing messages field
        }
        
        response = client.post('/chat/completions', 
                             json=invalid_request,
                             content_type='application/json')
        
        assert response.status_code == 400

    def test_chat_completions_handles_streaming(self, client, sample_streaming_request):
        """Test that /chat/completions handles streaming requests"""
        response = client.post('/chat/completions', 
                             json=sample_streaming_request,
                             content_type='application/json')
        
        # Should return some response
        assert response.status_code in [200, 502, 503, 504]

    def test_chat_completions_returns_openai_format(self, client, sample_chat_request):
        """Test that /chat/completions returns OpenAI-compatible format"""
        with patch('main.forward_request') as mock_forward:
            mock_forward.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Hello! I'm doing well, thank you for asking."
                    },
                    "finish_reason": "stop",
                    "index": 0
                }],
                "model": "gpt-3.5-turbo",
                "object": "chat.completion",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 15,
                    "total_tokens": 25
                }
            }
            
            response = client.post('/chat/completions', 
                                 json=sample_chat_request,
                                 content_type='application/json')
            
            data = response.get_json()
            assert 'choices' in data
            assert isinstance(data['choices'], list)
            assert len(data['choices']) > 0
            assert 'message' in data['choices'][0]
            assert 'content' in data['choices'][0]['message']

    def test_chat_completions_url_construction(self, client, sample_chat_request):
        """Test that /chat/completions uses correct URL construction"""
        with patch('proxy_client.ProxyClient.forward_request') as mock_forward:
            # Mock successful response
            mock_forward.return_value = {
                "choices": [{
                    "message": {"role": "assistant", "content": "Test response"},
                    "finish_reason": "stop",
                    "index": 0
                }]
            }
            
            response = client.post('/chat/completions', 
                                 json=sample_chat_request,
                                 content_type='application/json')
            
            # Verify the mock was called with correct parameters
            mock_forward.assert_called_once()
            call_args = mock_forward.call_args
            
            # Check that endpoint was passed as empty string to use target URL directly
            assert call_args[1]['endpoint'] == ""
            # Check that method was POST (default)
            assert call_args[1]['method'] == "POST"

    def test_error_response_format(self, client, sample_chat_request):
        """Test that error responses follow OpenAI format"""
        with patch('main.forward_request') as mock_forward:
            mock_forward.side_effect = Exception("Test error")
            
            response = client.post('/chat/completions', 
                                 json=sample_chat_request,
                                 content_type='application/json')
            
            data = response.get_json()
            assert 'error' in data
            assert 'message' in data['error']

    def test_cors_headers(self, client):
        """Test that CORS headers are properly set"""
        response = client.get('/models')
        assert 'Access-Control-Allow-Origin' in response.headers

    def test_content_type_headers(self, client, sample_chat_request):
        """Test that content-type headers are properly set"""
        response = client.post('/chat/completions', 
                             json=sample_chat_request,
                             content_type='application/json')
        
        assert 'Content-Type' in response.headers
        assert 'application/json' in response.headers['Content-Type']

    def test_request_logging(self, client, sample_chat_request):
        """Test that requests are properly logged"""
        with patch('main.forward_request') as mock_forward:
            mock_forward.return_value = {"choices": []}
            with patch('main.logger') as mock_logger:
                client.post('/chat/completions', 
                           json=sample_chat_request,
                           content_type='application/json')
                
                # Verify that logging was called
                assert mock_logger.info.called or mock_logger.debug.called

    def test_invalid_json_handling(self, client):
        """Test handling of invalid JSON in request body"""
        response = client.post('/chat/completions', 
                             data="invalid json",
                             content_type='application/json')
        
        assert response.status_code == 400

    def test_missing_content_type(self, client, sample_chat_request):
        """Test handling of requests without content-type header"""
        response = client.post('/chat/completions', 
                             json=sample_chat_request)
        
        # Should still work or return appropriate error
        assert response.status_code in [200, 400, 502, 503, 504]

    def test_large_request_handling(self, client):
        """Test handling of very large requests"""
        large_request = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "x" * 1000000}  # 1MB message
            ],
            "temperature": 0.7,
            "max_tokens": 100,
            "stream": False
        }
        
        response = client.post('/chat/completions', 
                             json=large_request,
                             content_type='application/json')
        
        # Should handle gracefully (either process or return appropriate error)
        assert response.status_code in [200, 400, 413, 502, 503, 504]

    def test_concurrent_requests(self, client, sample_chat_request):
        """Test handling of concurrent requests"""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.post('/chat/completions', 
                                 json=sample_chat_request,
                                 content_type='application/json')
            results.append(response.status_code)
        
        # Start multiple concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should complete (not necessarily successfully)
        assert len(results) == 5
        for status_code in results:
            assert status_code in [200, 400, 502, 503, 504]

    def test_request_timeout_handling(self, client, sample_chat_request):
        """Test handling of request timeouts"""
        with patch('main.forward_request') as mock_forward:
            mock_forward.side_effect = TimeoutError("Request timeout")
            
            response = client.post('/chat/completions', 
                                 json=sample_chat_request,
                                 content_type='application/json')
            
            assert response.status_code == 502

    def test_memory_usage_under_load(self, client, sample_chat_request):
        """Test memory usage doesn't grow excessively under load"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss
            
            # Make multiple requests
            for _ in range(10):
                client.post('/chat/completions', 
                           json=sample_chat_request,
                           content_type='application/json')
            
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            
            # Memory increase should be reasonable (< 50MB)
            assert memory_increase < 50 * 1024 * 1024
        except ImportError:
            # Skip test if psutil is not available
            pytest.skip("psutil not available")
