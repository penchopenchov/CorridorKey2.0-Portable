CORRIDORKEY 2.0 PORTABLE - START HERE
===================================

COPY THIS WHOLE FOLDER TO YOUR OTHER PC

The application runs directly from the repository folder (CorridorKey 2.0 on
this installation). Copy it intact and keep its files together, including
runtime/, weights/, vfms/ and ffmpeg.exe. No portable subfolder, separate
Python installation or CUDA toolkit is needed. Run it from a local folder.

The other PC needs compatible Windows x64, a supported NVIDIA GPU and a
compatible NVIDIA driver. The app does not install a GPU driver.

HOW TO PROCESS A CLIP

1. Double-click CorridorKey_DRAG_CLIPS_HERE.bat.
2. Drag your original video into the terminal and press Enter. You can also
   drop a clip directly onto the BAT in File Explorer.
3. Choose how your SOURCE was exported:
     1 = sRGB
     2 = Rec.709 with BT.709 transfer
     3 = Linear Rec.709 / gamma 1.0
   For your LINEAR REC.709 PRORES 4444 footage, choose 3. A MOV/MP4 filename or
   the ProRes codec alone does not tell you which color setting is correct.
4. Leave video levels on Auto unless you know the source needs Full or Limited.
5. Choose your matte:
     1 = No matte; let the model find the foreground.
     2 = A mask for the first frame.
     3 = A full matte video or image sequence covering the shot.
   For a rough AE roto video, choose 3 and use matte trust 0.75 initially.
   Leave authoritative matte mode off initially for a rough roto.
6. Choose Video or EXR output. The Video cutout is a ProRes 4444 MOV with
   transparency. EXR is a scene-linear image sequence with RGBA for cutout.
7. Choose outputs by number, or press Enter for all four:
     1 = alpha: black-and-white coverage mask
     2 = fg: foreground RGB without embedded transparency
     3 = cutout: foreground WITH transparency; use this in your editor
     4 = checker: checkerboard preview for checking edges
8. For video cutout, choose OUTPUT color separately: straight sRGB for standard
   editing, or straight linear Rec.709 for your linear compositing pipeline.
   EXR output is always linear. Keep despill at 0.5 initially.
9. Keep GPU memory on Auto. For a first test, enter a frame limit of 24 or 48.
10. Choose an output parent and a temporary-cache drive, or accept defaults.
    The default output is out_CLIPNAME beside the source clip. Long 4K shots
    need substantial temporary disk space for decoded float frames.
11. If using a matte, confirm a discovered companion or drag in your mask path
    when asked. Then review the settings and confirm Start.

Do not close the terminal until processing finishes. Import the cutout MOV
into your editor; select Straight / Unmatted alpha if it asks. Keep your
original audio in the editing timeline.

The progress line shows the clip number, current stage, stage percentage,
frames processed/total, elapsed time and estimated time remaining for that
stage. Each stage starts its own counter. Loading, finalization and cleanup
show elapsed time and "estimating" when a percentage cannot be measured.
Normal inference combines inference and rendering; low-VRAM mode shows them
separately. A stage reaching 100% does not mean the entire clip has finished.
Wait for the final completion message. Redirected logs get periodic updates.
During GPU processing, VRAM shows allocated/reserved PyTorch memory in GiB:
active tensor memory / total allocator memory including its reusable cache.
These are this worker's figures, excluding driver overhead and other apps.

HOW TO GIVE IT YOUR AFTER EFFECTS ROTO

Export a separate movie that visibly shows WHITE for the subject and BLACK
for the background. Gray is partial coverage. It must match the original
clip's dimensions, FPS, starting frame and duration. An MP4 matte is supported;
use a high-quality encode for cleaner edges. ProRes also works.

Example companion names placed next to one another:
  shot.mov                  original footage
  shot_AlphaHint.mp4        full black-and-white roto movie
  shotFrameHint.png         optional first-frame mask instead

For a full video matte, the black-and-white PICTURE supplies the mask. A
normal color cutout with transparency only in its embedded alpha is not the
same input. See README_ADVANCED.txt for the AE Shift Channels export recipe.

IF SOMETHING GOES WRONG

- GPU out of memory: close other GPU-heavy apps, choose manual low-VRAM mode,
  and try an 8-frame chunk / 4-frame stride or a smaller window.
- Matte mismatch: check FPS, frame alignment and that the mask covers the shot.
- Missing files: copy the COMPLETE portable folder, including runtime, weights,
  vfms, third_party, corridorkey and ffmpeg.exe.
- OpenEXR error on an older copy: use this updated BAT and launcher together.
  This package enables EXR support before OpenCV is loaded.

MORE INFORMATION

README_ADVANCED.txt         Detailed color, matte, export and command-line guide.
changelog.txt               Full explanation of the source changes and fixes.
LICENSE                    Upstream software/model license.
THIRD_PARTY_NOTICES.md      Foundation-model and other third-party notices.

The portable runtime and models are included here, but intentionally excluded
from normal source Git commits. This installed folder is the runnable package;
a source-only GitHub clone requires setup or the installed payload separately.
