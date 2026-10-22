import contextlib
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import cv2
import numpy as np

ROOT = next((parent for parent in Path(__file__).resolve().parents
             if (parent / 'infer.py').is_file() and (parent / 'ffmpeg.exe').is_file()),
            Path(__file__).resolve().parents[1])
FFMPEG = ROOT / 'ffmpeg.exe'


class LauncherTests(unittest.TestCase):
    def launcher(self):
        self.assertIsNotNone(importlib.util.find_spec('corridorkey_launcher'),
                             'The approved color-aware launcher is not implemented yet')
        return importlib.import_module('corridorkey_launcher')

    def test_fresh_process_decodes_mp4_without_inherited_exr_enablement(self):
        # The main test process enables EXR for its fixtures. A real BAT starts
        # fresh, so verify the launcher itself enables EXR before probing video.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            clip = folder / 'shot.mp4'
            subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-f', 'lavfi',
                            '-i', 'color=c=gray:s=128x64:r=24', '-frames:v', '2',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)],
                           check=True, capture_output=True)
            script = (
                'import sys; from pathlib import Path; import corridorkey_launcher as launcher; '
                'prepared=launcher.decode_video(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[4],"auto",2,Path(sys.argv[3])); '
                'import cv2; frames=sorted(prepared.path.glob("*.exr")); '
                'assert len(frames)==2; '
                'assert cv2.imread(str(frames[0]),cv2.IMREAD_UNCHANGED).shape==(64,128,3); '
                'print("Fresh MP4 decoding passed")'
            )
            for color in ('srgb', 'rec709'):
                for inherited in (None, '0'):
                    with self.subTest(color=color, inherited_exr=inherited):
                        environment = os.environ.copy()
                        environment.pop('OPENCV_IO_ENABLE_OPENEXR', None)
                        if inherited is not None:
                            environment['OPENCV_IO_ENABLE_OPENEXR'] = inherited
                        destination = folder / f'{color}_{inherited}'
                        result = subprocess.run([sys.executable, '-c', script, str(clip),
                                                 str(destination), str(FFMPEG), color],
                                                cwd=ROOT, env=environment, capture_output=True,
                                                text=True, timeout=60)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn('Fresh MP4 decoding passed', result.stdout)

    def test_linear_prores_preserves_midtones_precision_fps_and_frame_count(self):
        launcher = self.launcher()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            # A shallow ramp reveals accidental 8-bit decoding as well as double gamma.
            ramp = np.linspace(0.15, 0.21, 128, dtype=np.float32)
            rgb = np.broadcast_to(ramp[None, :, None], (64, 128, 3)).copy()
            plate = folder / 'plate.exr'
            self.assertTrue(cv2.imwrite(str(plate), rgb))
            clip = folder / 'linear plate.mov'
            subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-loop', '1',
                            '-framerate', '24000/1001', '-i', str(plate), '-frames:v', '3',
                            '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv444p12le',
                            '-c:v', 'prores_ks', '-profile:v', '4', '-color_primaries', 'bt709',
                            '-colorspace', 'bt709', '-color_trc', 'linear', '-color_range', 'tv',
                            str(clip)], check=True, capture_output=True)
            prepared = launcher.decode_video(clip, folder / 'decoded', 'linear', 'auto', 2, FFMPEG)
            frames = sorted(prepared.path.glob('*.exr'))
            self.assertEqual(len(frames), 2)
            self.assertAlmostEqual(prepared.fps, 24000 / 1001, places=4)
            decoded = cv2.imread(str(frames[0]), cv2.IMREAD_UNCHANGED)
            self.assertEqual(decoded.shape, rgb.shape)
            self.assertLess(float(np.abs(decoded - rgb).max()), 0.004)
            self.assertGreater(len(np.unique(decoded[32, :, 0])), 90)

    def test_srgb_and_rec709_are_decoded_once_to_linear(self):
        launcher = self.launcher()
        x = np.array([0.0, 0.02, 0.18, 0.5, 1.0], dtype=np.float32)
        np.testing.assert_allclose(launcher.decode_transfer(x, 'linear'), x)
        expected_srgb = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
        expected_709 = np.where(x < 0.081, x / 4.5, ((x + 0.099) / 1.099) ** (1 / 0.45))
        np.testing.assert_allclose(launcher.decode_transfer(x, 'srgb'), expected_srgb, atol=1e-6)
        np.testing.assert_allclose(launcher.decode_transfer(x, 'rec709'), expected_709, atol=1e-6)

    def test_rec709_video_uses_inverse_bt709_transfer_for_midgray(self):
        launcher = self.launcher()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            plate = folder / 'gray.exr'
            self.assertTrue(cv2.imwrite(str(plate), np.full((64, 128, 3), 0.5, np.float32)))
            clip = folder / 'rec709.mov'
            subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-i', str(plate),
                            '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv444p12le',
                            '-c:v', 'prores_ks', '-profile:v', '4', '-colorspace', 'bt709',
                            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                            str(clip)], check=True, capture_output=True)
            result = launcher.decode_video(clip, folder / 'decoded', 'rec709', 'auto', 1, FFMPEG)
            actual = cv2.imread(str(next(result.path.glob('*.exr'))), cv2.IMREAD_UNCHANGED)
            # Hand-derived inverse BT.709 OETF at encoded value 0.5, allowing ProRes quantization.
            self.assertAlmostEqual(float(actual.mean()), 0.2595894, delta=0.004)

    def test_terminal_menu_selects_linear_input_and_first_frame_matte(self):
        launcher = self.launcher()
        # Input color, levels, matte, trust, format, outputs, cutout color,
        # despill, memory, frame limit, output root, cache root.
        answers = ['3', '1', '2', '0.95', '1', '1 3', '2', '0.5', '1', '4', '', '']
        with patch('builtins.input', side_effect=answers), contextlib.redirect_stdout(io.StringIO()) as output:
            settings = launcher.prompt_settings(has_sequences=False)
        self.assertEqual(settings.input_color, 'linear')
        self.assertEqual(settings.hint_mode, 'first')
        self.assertEqual(settings.outputs, ('alpha', 'cutout'))
        self.assertTrue(settings.cutout_linear)
        self.assertEqual(settings.num_frames, 4)
        self.assertIn('Linear Rec.709', output.getvalue())

    def test_accepting_menu_defaults_processes_all_frames(self):
        launcher = self.launcher()
        with patch('builtins.input', side_effect=[''] * 11), contextlib.redirect_stdout(io.StringIO()):
            settings = launcher.prompt_settings(has_sequences=False)
        self.assertEqual(settings.num_frames, -1)
        self.assertEqual(settings.hint_mode, 'none')

    def test_no_matte_ignores_companion_and_full_matte_requires_a_real_path(self):
        launcher = self.launcher()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'shot.mov'
            source.touch()
            (Path(tmp) / 'shotFrameHint.png').touch()
            job = launcher.Job(source, source)
            with patch('builtins.input', side_effect=AssertionError('No-matte mode must not prompt for a hint')):
                self.assertIsNone(launcher.resolve_hint(job, 'none'))
            matte = Path(tmp) / 'matte.mov'
            matte.touch()
            with patch('builtins.input', side_effect=[str(Path(tmp) / 'missing.mov'), str(matte)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.resolve_hint(job, 'full'), matte)

    def test_command_routes_linear_frames_and_full_matte_into_exr_export(self):
        launcher = self.launcher()
        settings = launcher.Settings(input_color='linear', hint_mode='full',
                                     output_format='exr', outputs=('alpha', 'cutout'),
                                     authoritative=True, num_frames=4)
        prepared = launcher.PreparedMedia(Path('frames'), 24000 / 1001)
        command = launcher.inference_command(prepared, Path('matte_frames'), Path('result'), settings, FFMPEG)
        self.assertIn('--frame_dir_linear', command)
        self.assertIn('--no_carry_hint', command)
        self.assertEqual(command[command.index('--hint_video') + 1], 'matte_frames')
        self.assertEqual(command[command.index('--output_format') + 1], 'exr')
        self.assertAlmostEqual(float(command[command.index('--frame_dir_fps') + 1]), 24000 / 1001)

    def test_flat_and_input_subfolder_sequences_are_both_recognized(self):
        launcher = self.launcher()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            flat = base / 'flat'
            nested = base / 'nested' / 'Input'
            flat.mkdir()
            nested.mkdir(parents=True)
            (flat / '000001.png').touch()
            (nested / '000001.exr').touch()
            jobs = launcher.collect_jobs([flat, nested.parent])
            self.assertEqual([job.input_path for job in jobs], [flat, nested])

    def test_batch_with_companion_png_keeps_video_as_source(self):
        launcher = self.launcher()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            clip = folder / 'shot.mov'
            clip.touch()
            (folder / 'shotFrameHint.png').touch()
            jobs = launcher.collect_jobs([folder])
            self.assertEqual([job.input_path for job in jobs], [clip])

    def test_full_matte_mode_does_not_accept_first_frame_companion(self):
        launcher = self.launcher()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            clip = folder / 'shot.mov'
            clip.touch()
            (folder / 'shot_AlphaHint.png').touch()
            matte = folder / 'full.mov'
            matte.touch()
            with patch('builtins.input', side_effect=[str(matte)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.resolve_hint(launcher.Job(clip, clip), 'full'), matte)


if __name__ == '__main__':
    unittest.main()
