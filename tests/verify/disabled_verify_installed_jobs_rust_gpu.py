# DISABLED (TODO 94a2fa2): not flaky, not hardware/network/API-cost
# in the sense TODO b2ab79f/9bc522b/0d91c74/b6abde2's own disabled_
# scripts are -- disabled purely for real wall-clock cost: the first
# `cargo build --release` here fetches and compiles the `wgpu` crate
# and its ~40-crate dependency tree (confirmed ~30s the first time,
# under a second on every later run once cargo's own registry cache is
# warm). That's too slow for the normal regression sweep but is real,
# working, non-mocked coverage of an actual GPU compute shader running
# end to end through the real Installed Jobs pipeline -- run directly
# (`.venv/bin/python3
# tests/verify/disabled_verify_installed_jobs_rust_gpu.py`) when you
# want this coverage (needs a real GPU and network access to
# crates.io for the first build).
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import desk.shell.widget_frame  # noqa: E402  (imported before QApplication -- WebEngine ordering)
import desk.shell.canvas  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from desk.desks import Desk  # noqa: E402
from desk.installed_jobs import InstalledJobDefinition, compute_version_hash, installed_job_dir  # noqa: E402
from desk.shell.window import DeskWindow  # noqa: E402

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


def _git_init(directory):
    subprocess.run(["git", "init", "-q"], cwd=directory, check=True)


# The confirmed-working GPU probe from plans/installed-jobs-rust-gpu.md's
# own investigation, adapted into the Installed Jobs shape: dispatches a
# real WGSL compute shader that doubles a 16-element f32 array on the
# actual GPU and reads the result back.
_CARGO_TOML = """[package]
name = "gpu_double"
version = "0.1.0"
edition = "2021"

[dependencies]
wgpu = "0.19"
pollster = "0.3"
"""

_MAIN_RS = r"""
use wgpu::util::DeviceExt;

const SHADER: &str = r#"
@group(0) @binding(0) var<storage, read_write> data: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    data[id.x] = data[id.x] * 2.0;
}
"#;

fn main() {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor {
        backends: wgpu::Backends::all(),
        ..Default::default()
    });
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance,
        compatible_surface: None,
        force_fallback_adapter: false,
    }))
    .expect("no adapter");
    let info = adapter.get_info();
    println!("GPU_ADAPTER_FOUND name={} backend={:?}", info.name, info.backend);

    let (device, queue) = pollster::block_on(adapter.request_device(&Default::default(), None))
        .expect("no device");

    let input: Vec<f32> = (0..16).map(|i| i as f32).collect();

    let module = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: Some("double"),
        source: wgpu::ShaderSource::Wgsl(SHADER.into()),
    });

    let buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
        label: Some("data"),
        contents: unsafe { std::slice::from_raw_parts(input.as_ptr() as *const u8, input.len() * 4) },
        usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
    });
    let staging = device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("staging"),
        size: buffer.size(),
        usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });

    let bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: None,
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::COMPUTE,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Storage { read_only: false },
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        }],
    });
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: None,
        layout: &bind_group_layout,
        entries: &[wgpu::BindGroupEntry { binding: 0, resource: buffer.as_entire_binding() }],
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: None,
        bind_group_layouts: &[&bind_group_layout],
        push_constant_ranges: &[],
    });
    let pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
        label: None,
        layout: Some(&pipeline_layout),
        module: &module,
        entry_point: "main",
    });

    let mut encoder = device.create_command_encoder(&Default::default());
    {
        let mut pass = encoder.begin_compute_pass(&Default::default());
        pass.set_pipeline(&pipeline);
        pass.set_bind_group(0, &bind_group, &[]);
        pass.dispatch_workgroups(1, 1, 1);
    }
    encoder.copy_buffer_to_buffer(&buffer, 0, &staging, 0, buffer.size());
    queue.submit(Some(encoder.finish()));

    let slice = staging.slice(..);
    let (tx, rx) = std::sync::mpsc::channel();
    slice.map_async(wgpu::MapMode::Read, move |r| tx.send(r).unwrap());
    device.poll(wgpu::Maintain::Wait);
    rx.recv().unwrap().unwrap();
    let data = slice.get_mapped_range();
    let result: &[f32] =
        unsafe { std::slice::from_raw_parts(data.as_ptr() as *const f32, data.len() / 4) };
    let expected: Vec<f32> = input.iter().map(|x| x * 2.0).collect();
    let matches = result.iter().zip(expected.iter()).all(|(a, b)| (a - b).abs() < 1e-6);
    println!("OUTPUT {:?}", result);
    println!("SHADER_RESULT_CORRECT={}", matches);
}
"""


def test_real_gpu_compute_shader_end_to_end():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        directory = Path(d)
        _git_init(directory)
        job_dir = installed_job_dir(directory, "gpu_double")
        (job_dir / "src").mkdir(parents=True)
        (job_dir / "Cargo.toml").write_text(_CARGO_TOML)
        (job_dir / "src" / "main.rs").write_text(_MAIN_RS)

        class _FakeWindowForRun:
            def __init__(self) -> None:
                real_hash = compute_version_hash(job_dir)
                self.current_desk = Desk(
                    path=directory / "default.desk",
                    installed_jobs=[
                        InstalledJobDefinition(
                            name="gpu_double", version_hash=real_hash, installed_at="2026-01-01T00:00:00"
                        )
                    ],
                )
                self._schema_registry = type("S", (), {"get": lambda self, k: None})()

            def _confirm_fn(self, title, message):
                return lambda: True

            def save_current_desk(self) -> None:
                pass

            @property
            def _event_mediator(self):
                return type("M", (), {"publish": lambda self, *a, **k: None})()

            get_installed_job = DeskWindow.get_installed_job
            get_installed_job_for_run = DeskWindow.get_installed_job_for_run
            run_installed_job = DeskWindow.run_installed_job
            get_state = DeskWindow.get_state
            _resolve_job_needs = DeskWindow._resolve_job_needs

        window = _FakeWindowForRun()
        results = []
        window.run_installed_job(
            "gpu_double", None, lambda ok, out, err, tb: results.append((ok, out, err, tb))
        )
        deadline = time.time() + 300.0  # first build can be slow
        while time.time() < deadline and not results:
            time.sleep(0.1)
        check("the job eventually reports a result", bool(results))
        if results:
            ok, stdout, stderr, tb = results[0]
            check("the job ran successfully", ok)
            check("a real GPU adapter was found", "GPU_ADAPTER_FOUND name=" in stdout)
            check(
                "the compute shader's own output is the correct doubled values",
                "SHADER_RESULT_CORRECT=true" in stdout,
            )


test_real_gpu_compute_shader_end_to_end()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
