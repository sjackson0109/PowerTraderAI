# A3: Hardware inventory (PTAI-RD-001 M0, Deliverable A)

Measured on the owner's workstation on 2026-11-11 with Windows' CIM classes (`Win32_Processor`, `Win32_ComputerSystem`, `Win32_VideoController`, `Get-Volume`, `Get-PhysicalDisk`) and `psutil`. `nvidia-smi` is not installed. The research engine (`app/research_engine/resources.py`) reports the same figures in Settings > Training > "Research engine...".

| Resource | Measured | What it means for research |
|---|---|---|
| Computer | GMKtec NucBox K8 Plus, Windows 11 Pro 10.0.26200 | A desktop: one machine runs the hub, the trader and research together |
| Processor | AMD Ryzen 7 8845HS w/ Radeon 780M Graphics: 8 cores, 16 threads, 3.8 GHz base | CPU-bound replays and tree models parallelise well across processes. Balanced mode runs 4 jobs at once; maximum throughput runs 7 |
| Memory | 32 GiB (31.8 GiB visible) | Shared with the integrated GPU. See the measurement below |
| GPU | AMD Radeon 780M (integrated, shared memory) | No CUDA. A torch model could use DirectML only through `torch-directml`, which is not installed. No model in the programme needs a GPU yet |
| Model accelerators found | none | Models run on the processor. Not probed: AMD's on-chip NPU, which no installed framework uses |
| Storage | Samsung 990 PRO 2 TB NVMe, NTFS; 1,056 GiB free on C: | Room for years of minute bars and immutable dataset snapshots |
| Python (research) | CPython 3.13 | The same version as CI (`.github/workflows/ci-cd.yml`) |

## Memory available while the owner works

At 18:00 UTC on 2026-11-11, with the owner's usual programs running, psutil reported **2.1 GiB available (93% used)**:
- `llama-server`: 6.8 GiB private;
- VS Code: about 5 GiB private across its four largest processes;
- Chrome: about 2.7 GiB across its six largest;
- the hub and its trader processes: about 0.25 GiB working set;
- a full test-suite run: 2.3 GiB private.

Every mode of the research engine keeps at least max(4 GiB, a share of memory) free (`resources.limits_for`), so at that moment the engine starts no job, and its window says why. This is by design: research must not starve the trader. Long batches are best run when `llama-server` is stopped, or in low-resource mode (one job; keeps 40% free).

## Python environment of the owner's app

From the capability matrix (A1 §4): the app's `.venv` lacks **scikit-learn**, which `app/requirements.txt` and CI require. So the trained contestants in Settings > Training > "Compare models..." cannot run in the owner's app. Installing it changes the owner's environment, so it is listed as owner decision O6 in D.

## Energy

No sensor is read: Windows gives programs no processor power reading without a driver. The engine records each job's processor time. It estimates energy (Wh) only when the owner enters the watts one busy core draws, and cost only when they enter a price per kWh. No tariff is assumed.
