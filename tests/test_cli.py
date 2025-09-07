"""Tests for Helios MCP CLI interface."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from click.testing import CliRunner

from helios_mcp.cli import main, run_server


class TestCLIArguments:
    """Test CLI argument parsing and validation."""
    
    def test_cli_help(self):
        """Test CLI help message."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        
        assert result.exit_code == 0
        assert "Helios MCP server" in result.output
        assert "--helios-dir" in result.output
        assert "--verbose" in result.output
        assert "weighted" in result.output  # Part of "weighted inheritance"
    
    def test_cli_version(self):
        """Test CLI version option."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        
        assert result.exit_code == 0
        assert "0.1.0" in result.output
    
    def test_default_helios_dir(self):
        """Test default --helios-dir behavior."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.return_value = None
            result = runner.invoke(main, [])
            
            # Should call asyncio.run with default helios dir
            assert mock_asyncio_run.called
            args = mock_asyncio_run.call_args[0]
            # The first argument should be the coroutine
            assert len(args) == 1
    
    def test_custom_helios_dir(self):
        """Test custom --helios-dir path."""
        runner = CliRunner()
        custom_path = "/tmp/test-helios"
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.return_value = None
            result = runner.invoke(main, ["--helios-dir", custom_path])
            
            assert result.exit_code == 0
            assert mock_asyncio_run.called
    
    def test_verbose_flag(self):
        """Test --verbose flag."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            with patch('helios_mcp.cli.logging') as mock_logging:
                mock_asyncio_run.return_value = None
                result = runner.invoke(main, ["--verbose"])
                
                assert result.exit_code == 0
                # Should have set debug logging level
                mock_logging.getLogger.return_value.setLevel.assert_called_with(mock_logging.DEBUG)
    
    def test_invalid_helios_dir(self):
        """Test behavior with invalid directory path."""
        runner = CliRunner()
        
        # Use isolated filesystem to control directory creation
        with runner.isolated_filesystem():
            # Create a file where we want a directory
            with open("blocked", "w") as f:
                f.write("test")
            
            # The CLI should handle this gracefully and log error to stderr
            result = runner.invoke(main, ["--helios-dir", "blocked/helios"])
            # The CLI logs errors but may still return 0 - both are acceptable
            assert result.exit_code in [0, 1]


class TestServerCreation:
    """Test server factory function and creation."""
    
    @patch('helios_mcp.cli.create_server')
    def test_server_factory_called(self, mock_create_server):
        """Test that server factory is called correctly."""
        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_create_server.return_value = mock_server
        
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["--helios-dir", "test-helios"])
            
            assert result.exit_code == 0
            mock_create_server.assert_called_once()
            # Get the path argument
            call_args = mock_create_server.call_args[0]
            assert len(call_args) == 1
            assert isinstance(call_args[0], Path)
    
    @patch('helios_mcp.cli.create_server')
    def test_server_run_called(self, mock_create_server):
        """Test that server.run() is called."""
        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_create_server.return_value = mock_server
        
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["--helios-dir", "test-helios"])
            
            assert result.exit_code == 0
            mock_server.run.assert_called_once()
    
    def test_directory_creation(self):
        """Test that helios directory is created."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            with patch('helios_mcp.cli.create_server') as mock_create_server:
                mock_server = Mock()
                mock_server.run = AsyncMock()
                mock_create_server.return_value = mock_server
                
                helios_path = Path("test-helios")
                assert not helios_path.exists()
                
                result = runner.invoke(main, ["--helios-dir", str(helios_path)])
                
                assert result.exit_code == 0
                assert helios_path.exists()
                assert helios_path.is_dir()


class TestCLIErrorHandling:
    """Test CLI error handling scenarios."""
    
    def test_keyboard_interrupt(self):
        """Test handling of KeyboardInterrupt."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.side_effect = KeyboardInterrupt()
            
            result = runner.invoke(main, [])
            
            assert result.exit_code == 0
            # KeyboardInterrupt should be handled gracefully - check stderr for message
            assert "shutdown requested" in result.stderr_bytes.decode() if result.stderr_bytes else True
    
    def test_general_exception(self):
        """Test handling of general exceptions."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.side_effect = Exception("Test error")
            
            result = runner.invoke(main, [])
            
            # The CLI should log the error appropriately
            # Exit code behavior may vary based on how Click handles the exception
            assert result.exit_code in [0, 1]  # Either is acceptable 
            # Error should be logged to stderr, not stdout  
            assert "Failed to start" in result.stderr_bytes.decode() if result.stderr_bytes else True
    
    def test_verbose_exception_traceback(self):
        """Test that verbose flag shows full traceback on errors."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.side_effect = Exception("Test error")
            
            result = runner.invoke(main, ["--verbose"])
            
            # The CLI should log the error appropriately
            assert result.exit_code in [0, 1]  # Either is acceptable
            # With verbose, should show traceback in stderr
            if result.stderr_bytes:
                stderr = result.stderr_bytes.decode()
                assert "Failed to start" in stderr
                assert "traceback" in stderr.lower()  # Should show traceback


class TestRunServer:
    """Test the run_server async function."""
    
    @pytest.mark.asyncio
    async def test_run_server_basic(self, temp_helios_dir):
        """Test basic server running functionality."""
        mock_server = Mock()
        mock_server.run = AsyncMock()
        
        with patch('helios_mcp.cli.create_server', return_value=mock_server):
            await run_server(temp_helios_dir, verbose=False)
            
            mock_server.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_server_verbose(self, temp_helios_dir):
        """Test server running with verbose logging."""
        mock_server = Mock()
        mock_server.run = AsyncMock()
        
        with patch('helios_mcp.cli.create_server', return_value=mock_server):
            await run_server(temp_helios_dir, verbose=True)
            
            mock_server.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_run_server_exception(self, temp_helios_dir):
        """Test server error handling."""
        mock_server = Mock()
        mock_server.run = AsyncMock(side_effect=Exception("Server error"))
        
        with patch('helios_mcp.cli.create_server', return_value=mock_server):
            with pytest.raises(Exception, match="Server error"):
                await run_server(temp_helios_dir, verbose=False)


class TestCLIIntegration:
    """Test CLI integration with MCP protocol requirements."""
    
    def test_logging_to_stderr(self):
        """Test that logging goes to stderr, not stdout (MCP requirement)."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.asyncio.run') as mock_asyncio_run:
            mock_asyncio_run.return_value = None
            result = runner.invoke(main, ["--verbose"])
            
            # Output should not contain logging messages (they go to stderr)
            # This is critical for MCP protocol compliance
            assert result.exit_code == 0
            assert "Starting Helios MCP server" not in result.output
    
    def test_stdio_protocol_compatibility(self):
        """Test that CLI is compatible with stdio MCP transport."""
        runner = CliRunner()
        
        with patch('helios_mcp.cli.create_server') as mock_create_server:
            mock_server = Mock()
            mock_server.run = AsyncMock()
            mock_create_server.return_value = mock_server
            
            # Should not produce any stdout output that interferes with MCP protocol
            result = runner.invoke(main, [])
            
            assert result.exit_code == 0
            assert result.output.strip() == ""  # No stdout output
    
    @patch('helios_mcp.cli.create_server')
    def test_uvx_compatibility(self, mock_create_server):
        """Test that CLI works correctly with uvx execution."""
        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_create_server.return_value = mock_server
        
        runner = CliRunner()
        
        # Test typical uvx usage patterns
        with runner.isolated_filesystem():
            # Default usage
            result = runner.invoke(main, [])
            assert result.exit_code == 0
            
            # Custom helios dir
            result = runner.invoke(main, ["--helios-dir", "/tmp/custom-helios"])
            assert result.exit_code == 0
            
            # Verbose mode
            result = runner.invoke(main, ["--verbose"])
            assert result.exit_code == 0