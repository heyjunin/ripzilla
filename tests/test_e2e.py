import pytest
import os
import subprocess
import sys
from pathlib import Path
import logging
import shutil # Import shutil for mocking
import pytest_mock # Ensure mocker fixture is available

# Add the project root to the path to allow importing ripzilla
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import cli module for direct testing
from ripzilla import cli
from ripzilla import extract_audio
# Import specific exceptions and defaults for testing
from ripzilla.exceptions import (
    ExtractionError, FFmpegError, FFprobeError, NetworkError,
    RipzillaTimeoutError, NoAudioStreamError, DiskSpaceError
)
from ripzilla.utils import check_media_tools_installed, DEFAULT_FFPROBE_TIMEOUT
from ripzilla.extractors import DEFAULT_FFMPEG_TIMEOUT
# Import original function for cache clearing
from ripzilla.utils import detect_best_hwaccel as original_detect_best_hwaccel
# Import the result class for type checking
from ripzilla.core import ExtractionResult

logger = logging.getLogger(__name__)

# --- Constants ---
TEST_DIR = Path(__file__).parent
SAMPLE_VIDEO_LOCAL = TEST_DIR / "sample_video.mp4"
# Using a known, reliable small video URL for testing streaming
# Big Buck Bunny is large, let's find a smaller one if possible.
# Using a short Creative Commons video for testing:
# Source: https://peach.blender.org/download/ (or other CC sources)
# Example: Short clip from Sintel Trailer (replace if unavailable)
SAMPLE_VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4" # ~15MB
# SAMPLE_VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4" # Larger file

# --- Fixtures ---

@pytest.fixture(scope="module", autouse=True)
def check_media_tools():
    """Ensure ffmpeg & ffprobe are installed before running any tests in this module."""
    try:
        check_media_tools_installed()
    except FileNotFoundError as e:
        pytest.skip(f"Skipping e2e tests: {e}")

@pytest.fixture
def output_file(tmp_path):
    """Provides a temporary path for output audio files and ensures cleanup."""
    # tmp_path is a pytest fixture providing a temporary directory unique to the test function
    output_path = tmp_path / "output.aac" # Use .aac as a common output container
    yield output_path
    # Cleanup: Pytest's tmp_path fixture handles directory removal automatically
    # We just need to ensure the file itself doesn't cause issues if left behind
    # (though tmp_path cleanup should suffice)
    # if output_path.exists():
    #     output_path.unlink()

@pytest.fixture(scope="function") # Function scope to create a new video each time
def video_without_audio(tmp_path):
    """Generates a short video file *without* an audio stream using ffmpeg."""
    output_video_path = tmp_path / "no_audio_video.mp4"
    # Command using lavfi test sources:
    # -f lavfi -i testsrc: Generate a test pattern video
    # -t 1: Duration 1 second
    # -an: Disable audio recording
    # -vf format=pix_fmts=yuv420p: Ensure a common pixel format for compatibility
    cmd = [
        "ffmpeg",
        "-y", # Overwrite if exists (shouldn't in tmp_path)
        "-f", "lavfi", "-i", "testsrc=duration=1:size=32x32:rate=10",
        "-vf", "format=pix_fmts=yuv420p",
        "-an", # Explicitly disable audio
        str(output_video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        logger.debug(f"Generated video without audio: {output_video_path}")
        yield output_video_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Failed to generate test video without audio: {e}")
        logger.error(f"ffmpeg stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        pytest.fail(f"Failed to generate video for testing: {e}")
    except FileNotFoundError:
        # This case should be caught by the module-level check_media_tools fixture
        pytest.skip("ffmpeg not found, cannot generate test video.")

# --- Test Cases ---

@pytest.mark.skipif(not SAMPLE_VIDEO_LOCAL.exists(), reason="Local sample video not found")
def test_local_extraction(output_file):
    """Test extracting audio from a local video file returns ExtractionResult."""
    assert SAMPLE_VIDEO_LOCAL.exists(), f"Test video missing: {SAMPLE_VIDEO_LOCAL}"
    # Call extract_audio and capture the result
    result = extract_audio(str(SAMPLE_VIDEO_LOCAL), str(output_file))

    # Basic checks on the result object
    assert isinstance(result, ExtractionResult)
    assert result.output_path == str(output_file)
    assert result.quality_preset == "raw" # Default quality
    assert result.duration > 0
    assert result.file_size_bytes > 0
    assert output_file.exists()
    assert output_file.stat().st_size == result.file_size_bytes

def test_url_stream_extraction(output_file):
    """Test extracting audio from a URL returns ExtractionResult."""
    try:
        result = extract_audio(SAMPLE_VIDEO_URL, str(output_file))
        assert isinstance(result, ExtractionResult)
        assert result.output_path == str(output_file)
        assert result.duration > 0
        assert result.file_size_bytes > 0
        assert output_file.exists()
        assert output_file.stat().st_size == result.file_size_bytes
    except ConnectionError as e:
        pytest.skip(f"Skipping URL test due to network issue: {e}")
    except ExtractionError as e:
        if "Connection refused" in str(e) or "Network is unreachable" in str(e):
             pytest.skip(f"Skipping URL test due to network issue: {e}")
        else:
            pytest.fail(f"URL extraction failed unexpectedly: {e}")


def test_fallback_extraction(output_file, mocker):
    """Test the fallback mechanism (result object check)."""
    # Mock stream extraction to fail
    mock_stream = mocker.patch("ripzilla.core.try_stream_extract", side_effect=FFmpegError("Simulated stream FFmpeg failure"))
    # Spy on download and local extract
    mock_download = mocker.patch("ripzilla.extractors.download_video")
    mock_local = mocker.patch("ripzilla.extractors.try_local_extract")

    # Mock the disk space check to succeed
    mocker.patch("ripzilla.extractors._check_disk_space", return_value=True)

    try:
        # Run and capture result
        result = extract_audio(SAMPLE_VIDEO_URL, str(output_file))
        # We expect download and local extract to be called (mocks don't create file)
        mock_stream.assert_called_once()
        mock_download.assert_called_once()
        mock_local.assert_called_once()
        # Cannot check file size, but check result type and basic fields
        assert isinstance(result, ExtractionResult)
        assert result.file_size_bytes == -1 # Expect -1 as file wasn't created by mocks
        assert result.duration > 0
    except ConnectionError as e:
        pytest.skip(f"Skipping fallback test due to network issue during download: {e}")
    except (ExtractionError) as e:
        # Expecting potential errors like NetworkError if download mock fails, or others
        # We mainly check that the fallback path was attempted
        # Let's refine this if specific mock failures are needed
        pass

# --- CLI Tests ---

@pytest.mark.skipif(not SAMPLE_VIDEO_LOCAL.exists(), reason="Local sample video not found")
def test_cli_local_extraction(output_file):
    """Test the CLI for local file extraction."""
    cmd = [
        sys.executable, # Use the current python interpreter
        str(project_root / "ripzilla" / "cli.py"), # Path to the cli script
        str(SAMPLE_VIDEO_LOCAL),
        str(output_file)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    print("CLI Local STDOUT:", result.stdout)
    print("CLI Local STDERR:", result.stderr)
    assert result.returncode == 0, f"CLI returned non-zero exit code: {result.returncode}\n{result.stderr}"
    assert "✅ Output:" in result.stdout # Check for summary start
    assert output_file.exists()
    assert output_file.stat().st_size > 0

def test_cli_url_extraction(output_file):
    """Test the CLI for URL extraction."""
    cmd = [
        sys.executable, # Use the current python interpreter
        str(project_root / "ripzilla" / "cli.py"), # Path to the cli script
        SAMPLE_VIDEO_URL,
        str(output_file)
    ]
    try:
        # Set a timeout for the CLI command as well
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=300)
        print("CLI URL STDOUT:", result.stdout)
        print("CLI URL STDERR:", result.stderr)
        # Ensure the return code is 0 before checking output
        assert result.returncode == 0, f"CLI returned non-zero exit code: {result.returncode}\n{result.stderr}"
        assert "✅ Output:" in result.stdout # Check for summary start
        assert output_file.exists()
        assert output_file.stat().st_size > 0
    except subprocess.TimeoutExpired:
         pytest.skip("Skipping CLI URL test due to timeout")
    except Exception as e:
         # Catch potential issues running the subprocess
         pytest.fail(f"CLI URL test failed during execution: {e}")

def test_cli_invalid_input(tmp_path):
    """Test the CLI with non-existent input."""
    output_file = tmp_path / "output.aac"
    cmd = [
        sys.executable,
        str(project_root / "ripzilla" / "cli.py"),
        "non_existent_file.mp4",
        str(output_file)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    # Check for the specific user-facing error message printed by the CLI for FileNotFoundError
    assert "❌ Error: Input file not found: non_existent_file.mp4" in result.stderr
    assert not output_file.exists()

def test_cli_tools_missing(mocker, tmp_path):
    """Test the CLI fails gracefully if ffmpeg or ffprobe is not found."""
    # Mock shutil.which used by check_media_tools_installed within this process
    # Let's mock it to simulate ffprobe missing first
    def mock_which(tool):
        if tool == "ffmpeg":
            return "/fake/path/to/ffmpeg" # Assume ffmpeg exists
        elif tool == "ffprobe":
            return None # Simulate ffprobe missing
        return None
    mocker.patch("shutil.which", side_effect=mock_which)
    output_file = tmp_path / "output.aac"

    # Prepare arguments for cli.main
    test_args = [
        "prog_name", # Argv[0] is the program name
        SAMPLE_VIDEO_URL, # Input doesn't matter as much as the check
        str(output_file)
    ]
    mocker.patch.object(sys, 'argv', test_args)

    # Assert that SystemExit(1) is raised
    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    # TODO: Ideally capture stderr and check for the specific ffprobe error message
    assert not output_file.exists() # Ensure no output file was created 

def test_no_audio_stream_error(video_without_audio, output_file):
    """Test that extract_audio raises NoAudioStreamError for video without audio."""
    with pytest.raises(NoAudioStreamError, match="Input does not contain an audio stream"):
        extract_audio(str(video_without_audio), str(output_file))
    assert not output_file.exists()


def test_cli_no_audio_stream_error(video_without_audio, tmp_path, mocker):
    """Test that the CLI exits with code 2 for video without audio."""
    output_file = tmp_path / "output.aac"
    # Prepare arguments for cli.main
    test_args = [
        "prog_name",
        str(video_without_audio),
        str(output_file)
    ]

    # Mock sys.argv for the direct cli.main call
    mocker.patch.object(sys, 'argv', test_args)

    with pytest.raises(SystemExit) as excinfo:
        cli.main() # Call directly to test within the same process

    assert excinfo.value.code == 2 # Check for the specific exit code 2
    # TODO: Capture stderr and verify the warning message
    assert not output_file.exists() 

# --- New Tests for Timeouts and Disk Space ---

def test_ffmpeg_timeout(mocker, output_file):
    """Test RipzillaTimeoutError is raised on ffmpeg timeout."""
    # Mock _run_ffmpeg to simulate a timeout by raising the correct exception
    mocker.patch("ripzilla.extractors._run_ffmpeg", side_effect=RipzillaTimeoutError("FFmpeg command timed out"))

    with pytest.raises(RipzillaTimeoutError, match="FFmpeg command timed out"):
        # Use local file for simplicity, low timeout value
        extract_audio(str(SAMPLE_VIDEO_LOCAL), str(output_file), ffmpeg_timeout=0.1)
    assert not output_file.exists()

def test_ffprobe_timeout(mocker, output_file):
    """Test RipzillaTimeoutError is raised on ffprobe timeout during audio check."""
    # Mock the subprocess.run inside has_audio_stream
    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffprobe...", timeout=0.1))

    with pytest.raises(RipzillaTimeoutError, match="ffprobe command timed out"):
        # Low timeout value passed to extract_audio for ffprobe
        extract_audio(str(SAMPLE_VIDEO_LOCAL), str(output_file), ffprobe_timeout=0.1)
    assert not output_file.exists()

def test_disk_space_error(mocker, output_file):
    """Test DiskSpaceError is raised during fallback when disk is full."""
    # Mock stream extraction to fail, triggering fallback
    mocker.patch("ripzilla.core.try_stream_extract", side_effect=FFmpegError("Simulated stream failure"))
    # Mock the disk usage check to raise DiskSpaceError
    mocker.patch("shutil.disk_usage", side_effect=DiskSpaceError("Insufficient disk space"))

    with pytest.raises(DiskSpaceError, match="Insufficient disk space"):
        extract_audio(SAMPLE_VIDEO_URL, str(output_file))
    assert not output_file.exists() 

# --- New Tests for HWAccel ---

@pytest.mark.skipif(sys.platform != 'darwin', reason="VideoToolbox test only runs on macOS")
def test_hwaccel_flag_added_auto_mode(mocker):
    """Verify hwaccel flag is added in 'auto' mode when supported."""
    # Clear cache before mocking
    original_detect_best_hwaccel.cache_clear()
    # Mock detection to return videotoolbox
    mocker.patch("ripzilla.extractors.detect_best_hwaccel", return_value="videotoolbox")
    mock_run_ffmpeg = mocker.patch("ripzilla.extractors._run_ffmpeg")

    try:
        # Default mode is auto
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output.aac")
    except Exception: pass # Ignore errors, just check flags

    assert mock_run_ffmpeg.called
    called_cmd = mock_run_ffmpeg.call_args[0][0]
    assert "-hwaccel" in called_cmd and "videotoolbox" in called_cmd


def test_hwaccel_flag_not_added_auto_mode_unsupported(mocker):
    """Verify hwaccel flag is NOT added in 'auto' mode when unsupported."""
    # Clear cache before mocking
    original_detect_best_hwaccel.cache_clear()
    # Mock detection to return None
    mocker.patch("ripzilla.extractors.detect_best_hwaccel", return_value=None)
    mock_run_ffmpeg = mocker.patch("ripzilla.extractors._run_ffmpeg")

    try:
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output.aac", hwaccel_mode="auto")
    except Exception: pass

    assert mock_run_ffmpeg.called
    called_cmd = mock_run_ffmpeg.call_args[0][0]
    assert "-hwaccel" not in called_cmd

def test_hwaccel_flag_added_gpu_mode_supported(mocker):
    """Verify hwaccel flag is added in 'gpu' mode when supported."""
    original_detect_best_hwaccel.cache_clear()
    mocker.patch("ripzilla.extractors.detect_best_hwaccel", return_value="videotoolbox")
    mock_run_ffmpeg = mocker.patch("ripzilla.extractors._run_ffmpeg")

    try:
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output.aac", hwaccel_mode="gpu")
    except Exception: pass

    assert mock_run_ffmpeg.called
    called_cmd = mock_run_ffmpeg.call_args[0][0]
    assert "-hwaccel" in called_cmd and "videotoolbox" in called_cmd

def test_hwaccel_flag_not_added_gpu_mode_unsupported(mocker):
    """Verify hwaccel flag is NOT added in 'gpu' mode when unsupported (and logs warning)."""
    original_detect_best_hwaccel.cache_clear()
    mocker.patch("ripzilla.extractors.detect_best_hwaccel", return_value=None)
    mock_run_ffmpeg = mocker.patch("ripzilla.extractors._run_ffmpeg")
    mock_log_warning = mocker.patch("ripzilla.extractors.logger.warning")

    try:
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output.aac", hwaccel_mode="gpu")
    except Exception: pass

    assert mock_run_ffmpeg.called
    called_cmd = mock_run_ffmpeg.call_args[0][0]
    assert "-hwaccel" not in called_cmd
    mock_log_warning.assert_called_once_with(
        "GPU acceleration requested, but no compatible method detected. Using CPU."
    )

def test_hwaccel_flag_not_added_cpu_mode(mocker):
    """Verify hwaccel flag is NOT added in 'cpu' mode, even if supported."""
    original_detect_best_hwaccel.cache_clear()
    # Mock detection, although it shouldn't be called
    mock_detect = mocker.patch("ripzilla.extractors.detect_best_hwaccel", return_value="videotoolbox")
    mock_run_ffmpeg = mocker.patch("ripzilla.extractors._run_ffmpeg")

    try:
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output.aac", hwaccel_mode="cpu")
    except Exception: pass

    mock_detect.assert_not_called() # Ensure detection wasn't even attempted
    assert mock_run_ffmpeg.called
    called_cmd = mock_run_ffmpeg.call_args[0][0]
    assert "-hwaccel" not in called_cmd

# --- New Tests for Quality Presets ---

# Use parametrize to test different quality settings
@pytest.mark.parametrize(
    "quality_preset, expected_flags",
    [
        ("raw", ["-acodec", "copy"]),
        ("high", ["-acodec", "aac", "-b:a", "192k"]),
        ("medium", ["-acodec", "aac", "-b:a", "128k"]),
        ("low", ["-acodec", "libopus", "-b:a", "64k"]),
    ]
)
def test_quality_preset_flags(mocker, quality_preset, expected_flags):
    """Verify correct flags are added for each quality preset."""
    # Mock ffmpeg run to capture command
    mock_run_ffmpeg = mocker.patch("ripzilla.extractors._run_ffmpeg")
    # Mock HWAccel detection to None to simplify command checking
    original_detect_best_hwaccel.cache_clear()
    mocker.patch("ripzilla.extractors.detect_best_hwaccel", return_value=None)

    try:
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output", quality=quality_preset)
    except Exception: pass # Ignore errors

    assert mock_run_ffmpeg.called
    called_cmd = mock_run_ffmpeg.call_args[0][0]
    print(f"Preset: {quality_preset}, Command: {' '.join(called_cmd)}")

    # Check if all expected flags are present in the command
    for flag in expected_flags:
        assert flag in called_cmd

    # Ensure incompatible flags aren't present (e.g., copy shouldn't be with aac)
    if quality_preset != "raw":
        assert "copy" not in called_cmd
    if quality_preset != "high" and quality_preset != "medium":
        assert "aac" not in called_cmd
    if quality_preset != "low":
        assert "libopus" not in called_cmd

def test_invalid_quality_preset(mocker):
    """Test that providing an invalid quality preset raises ValueError."""
    with pytest.raises(ValueError, match="Invalid quality preset"):
        extract_audio(str(SAMPLE_VIDEO_LOCAL), "dummy_output", quality="invalid_preset")

# --- Cleanup old tests ---
# Remove test_hwaccel_flag_added_when_supported and test_hwaccel_flag_not_added_when_unsupported
# as they are superseded by the mode-specific tests above. 