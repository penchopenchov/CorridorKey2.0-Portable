CorridorKey 2.0 - portable Windows installation
=============================================

The final installed distribution is corridorkey-2_0-portable.
Its beginner guide is README.txt, detailed guide is README_ADVANCED.txt,
and fork handoff is AI_AGENT_INSTRUCTIONS.txt. This file is retained as source
documentation in the AI handoff; it is not a separate runtime dependency.

RUNNING

Double-click CorridorKey_DRAG_CLIPS_HERE.bat, or drop a clip/folder onto it.
No system Python, pip, uv, CUDA toolkit, environment activation, or online
model download is required once this complete folder is installed.

The other computer needs Windows x64, a supported NVIDIA GPU, and a compatible
NVIDIA display/compute driver. The portable runtime contains CUDA 12.8 PyTorch;
it does not install a GPU driver. More VRAM permits larger temporal windows.
This is a Windows package, not a macOS or Linux package.

COPYING TO ANOTHER PC

Copy this complete folder to a locally available drive on the other PC.
Keep these components together with their relative layout:

- CorridorKey_DRAG_CLIPS_HERE.bat, corridorkey_launcher.py, run_interactive.py,
  infer.py and the other application source files
- corridorkey/ and third_party/
- runtime/ (Python, DLLs, standard library and installed dependencies)
- weights/ and vfms/ (the model assets)
- ffmpeg.exe

The folder may be renamed or moved. runtime/python311._pth contains only
relative paths and isolates Python from the registry, user site packages,
PYTHONHOME and PYTHONPATH. The BAT resolves paths from its own location.
Its subprocesses use the same bundled interpreter.
The app-local Microsoft C++ runtime DLLs are also included in runtime/;
the installed payload does not rely on a separately installed VC++ runtime.

The repository's optional legacy venv, .git metadata, test results and download
caches are not required to run the portable app. A source-code-only Git clone
does not contain the ignored runtime, FFmpeg or model payloads; copying the
fully installed folder does. Ensure OneDrive files have actually downloaded
before copying them to another PC.

LINEAR REC.709 PRORES 4444

1. Drop your clip onto the BAT.
2. Choose input color 3: Linear Rec.709 / gamma 1.0.
3. Choose Auto video levels, or explicitly Full/Limited if known.
4. Select No matte, First-frame matte, or Full matte video/sequence.
5. Choose video export or EXR export and the outputs you want.
6. For video cutout, choose sRGB output or linear Rec.709 output independently.
7. Choose memory, frame limit, output folder and temporary cache location.
8. Review the settings, then start processing.

ProRes 4444 alone does not establish the input transfer function. Option 3 is
for material actually exported with linear RGB values. Option 2 applies the
inverse BT.709 OETF; it is not a generic gamma-2.4 / BT.1886 setting.

MATTES

No matte leaves subject selection to the model and ignores companion files.
First-frame matte accepts a mask image (or frame folder); white is subject,
black is background, and an image alpha channel can provide coverage.
Full matte accepts a grayscale coverage video or frame sequence. Matte values
are coverage and are not gamma-decoded. The matte video must match input FPS
and contain enough frames. Choose authoritative mode to use each supplied mask
instead of carried model predictions.

Existing source-video alpha is not automatically used as a matte.
Companion names are shotFrameHint.png and shot_AlphaHint.mov/mp4. The launcher
asks before using a discovered companion; otherwise drop your mask path in.

TEMPORARY SPACE AND EXPORTS

Decoded float EXR frames can use substantial temporary disk space, especially
for long 4K shots. Choose a cache drive with enough room. Each job's cache is
removed after completion, cancellation or failure. GPU features use that same
temporary job folder. Try 24-48 frames before processing an entire shot.

Video cutout is straight ProRes 4444 RGBA. Video values are clipped to [0,1].
EXR output preserves the runtime's scene-linear float values and uses RGBA for
cutout; choose half or full float. Other video outputs are H.264 previews.
Keep the original audio in your editing timeline.

DEVELOPERS / REBUILDING THE PORTABLE RUNTIME

The actual binary runtime and models are intentionally ignored by Git.
After following the upstream venv/dependency/model setup, run:

  powershell -File tools\make_portable.ps1

The builder copies the matching Windows CPython 3.11 base runtime and the
installed venv packages, adds an isolated relative python311._pth, removes
virtualenv-only startup hooks, and checks that all Python search paths stay
inside the application. It refuses to overwrite an existing runtime bundle.
It can take -SourceEnvironment and -PythonHome for an explicitly chosen source.
The build machine also needs the x64 Microsoft.VC143.CRT redistributable files
from Visual Studio / Build Tools. Discovery is automatic in standard VS folders;
otherwise supply -VCRedistDirectory with that CRT directory. These files are
copied app-locally and their actual loaded DLL locations are validated.

To run a source command with bundled Python:

  runtime\python.exe corridorkey_launcher.py
  runtime\python.exe -m unittest discover -s tests -v

See changelog.txt for the exact source change list and validation details.
