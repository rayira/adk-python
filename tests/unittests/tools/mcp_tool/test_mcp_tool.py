# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.auth_credential import AuthCredentialTypes
from google.adk.auth.auth_credential import HttpAuth
from google.adk.auth.auth_credential import HttpCredentials
from google.adk.auth.auth_credential import OAuth2Auth
from google.adk.auth.auth_credential import ServiceAccount
from google.adk.auth.auth_schemes import AuthScheme
from google.adk.auth.auth_schemes import AuthSchemeType
from google.adk.tools.mcp_tool.mcp_session_manager import MCPSessionManager
from google.adk.tools.mcp_tool.mcp_tool import MCPTool
from google.adk.tools.tool_context import ToolContext
from google.genai.types import FunctionDeclaration
import pytest


# Mock MCP Tool from mcp.types
class MockMCPTool:
  """Mock MCP Tool for testing."""

  def __init__(self, name="test_tool", description="Test tool description"):
    self.name = name
    self.description = description
    self.inputSchema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "First parameter"},
            "param2": {"type": "integer", "description": "Second parameter"},
        },
        "required": ["param1"],
    }


class TestMCPTool:
  """Test suite for MCPTool class."""

  def setup_method(self):
    """Set up test fixtures."""
    self.mock_mcp_tool = MockMCPTool()
    self.mock_session_manager = Mock(spec=MCPSessionManager)
    self.mock_session = AsyncMock()
    self.mock_session_manager.create_session = AsyncMock(
        return_value=self.mock_session
    )

  def test_init_basic(self):
    """Test basic initialization without auth."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    assert tool.name == "test_tool"
    assert tool.description == "Test tool description"
    assert tool._mcp_tool == self.mock_mcp_tool
    assert tool._mcp_session_manager == self.mock_session_manager

  def test_init_with_auth(self):
    """Test initialization with authentication."""
    # Create real auth scheme instances instead of mocks
    from fastapi.openapi.models import OAuth2

    auth_scheme = OAuth2(flows={})
    auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.OAUTH2,
        oauth2=OAuth2Auth(client_id="test_id", client_secret="test_secret"),
    )

    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
        auth_scheme=auth_scheme,
        auth_credential=auth_credential,
    )

    # The auth config is stored in the parent class _credentials_manager
    assert tool._credentials_manager is not None
    assert tool._credentials_manager._auth_config.auth_scheme == auth_scheme
    assert (
        tool._credentials_manager._auth_config.raw_auth_credential
        == auth_credential
    )

  def test_init_with_empty_description(self):
    """Test initialization with empty description."""
    mock_tool = MockMCPTool(description=None)
    tool = MCPTool(
        mcp_tool=mock_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    assert tool.description == ""

  def test_get_declaration(self):
    """Test function declaration generation."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    declaration = tool._get_declaration()

    assert isinstance(declaration, FunctionDeclaration)
    assert declaration.name == "test_tool"
    assert declaration.description == "Test tool description"
    assert declaration.parameters is not None

  @pytest.mark.asyncio
  async def test_run_async_impl_no_auth(self):
    """Test running tool without authentication."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    # Mock the session response
    expected_response = {"result": "success"}
    self.mock_session.call_tool = AsyncMock(return_value=expected_response)

    tool_context = Mock(spec=ToolContext)
    args = {"param1": "test_value"}

    result = await tool._run_async_impl(
        args=args, tool_context=tool_context, credential=None
    )

    assert result == expected_response
    self.mock_session_manager.create_session.assert_called_once_with(
        headers=None
    )
    # Fix: call_tool uses 'arguments' parameter, not positional args
    self.mock_session.call_tool.assert_called_once_with(
        "test_tool", arguments=args
    )

  @pytest.mark.asyncio
  async def test_run_async_impl_with_oauth2(self):
    """Test running tool with OAuth2 authentication."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    # Create OAuth2 credential
    oauth2_auth = OAuth2Auth(access_token="test_access_token")
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.OAUTH2, oauth2=oauth2_auth
    )

    # Mock the session response
    expected_response = {"result": "success"}
    self.mock_session.call_tool = AsyncMock(return_value=expected_response)

    tool_context = Mock(spec=ToolContext)
    args = {"param1": "test_value"}

    result = await tool._run_async_impl(
        args=args, tool_context=tool_context, credential=credential
    )

    assert result == expected_response
    # Check that headers were passed correctly
    self.mock_session_manager.create_session.assert_called_once()
    call_args = self.mock_session_manager.create_session.call_args
    headers = call_args[1]["headers"]
    assert headers == {"Authorization": "Bearer test_access_token"}

  @pytest.mark.asyncio
  async def test_get_headers_oauth2(self):
    """Test header generation for OAuth2 credentials."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    oauth2_auth = OAuth2Auth(access_token="test_token")
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.OAUTH2, oauth2=oauth2_auth
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, credential)

    assert headers == {"Authorization": "Bearer test_token"}

  @pytest.mark.asyncio
  async def test_get_headers_http_bearer(self):
    """Test header generation for HTTP Bearer credentials."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    http_auth = HttpAuth(
        scheme="bearer", credentials=HttpCredentials(token="bearer_token")
    )
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP, http=http_auth
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, credential)

    assert headers == {"Authorization": "Bearer bearer_token"}

  @pytest.mark.asyncio
  async def test_get_headers_http_basic(self):
    """Test header generation for HTTP Basic credentials."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    http_auth = HttpAuth(
        scheme="basic",
        credentials=HttpCredentials(username="user", password="pass"),
    )
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP, http=http_auth
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, credential)

    # Should create Basic auth header with base64 encoded credentials
    import base64

    expected_encoded = base64.b64encode(b"user:pass").decode()
    assert headers == {"Authorization": f"Basic {expected_encoded}"}

  @pytest.mark.asyncio
  async def test_get_headers_api_key(self):
    """Test header generation for API Key credentials."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    credential = AuthCredential(
        auth_type=AuthCredentialTypes.API_KEY, api_key="my_api_key"
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, credential)

    assert headers == {"X-API-Key": "my_api_key"}

  @pytest.mark.asyncio
  async def test_get_headers_no_credential(self):
    """Test header generation with no credentials."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, None)

    assert headers is None

  @pytest.mark.asyncio
  async def test_get_headers_service_account(self):
    """Test header generation for service account credentials."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    # Create service account credential
    service_account = ServiceAccount(scopes=["test"])
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.SERVICE_ACCOUNT,
        service_account=service_account,
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, credential)

    # Should return None as service account credentials are not supported for direct header generation
    assert headers is None

  @pytest.mark.asyncio
  async def test_run_async_impl_retry_decorator(self):
    """Test that the retry decorator is applied correctly."""
    # This is more of an integration test to ensure the decorator is present
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    # Check that the method has the retry decorator
    assert hasattr(tool._run_async_impl, "__wrapped__")

  @pytest.mark.asyncio
  async def test_get_headers_http_custom_scheme(self):
    """Test header generation for custom HTTP scheme."""
    tool = MCPTool(
        mcp_tool=self.mock_mcp_tool,
        mcp_session_manager=self.mock_session_manager,
    )

    http_auth = HttpAuth(
        scheme="custom", credentials=HttpCredentials(token="custom_token")
    )
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP, http=http_auth
    )

    tool_context = Mock(spec=ToolContext)
    headers = await tool._get_headers(tool_context, credential)

    assert headers == {"Authorization": "custom custom_token"}

  def test_init_validation(self):
    """Test that initialization validates required parameters."""
    # This test ensures that the MCPTool properly handles its dependencies
    with pytest.raises(TypeError):
      MCPTool()  # Missing required parameters

    with pytest.raises(TypeError):
      MCPTool(mcp_tool=self.mock_mcp_tool)  # Missing session manager
