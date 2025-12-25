
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

# Ranges of pitch changes (only positive for now, need to fix bug in matlab code)
pitch_array = [0, 2, 4, 6]

# Ranges for RPM and Mass flow rate (from excel calcs)
# for now having RPM dicated what mass flow rate would be
RPM_array = [9000, 10000, 12500, 15000, 17500]
mass_flow_array = [0.2232, 0.2480, 0.3100, 0.3720, 0.4340]

var_array = [pitch_array, RPM_array]


### Create configuration object for each combination of vars
@dataclass(frozen=True) # aids in not having to set up __init__, __repr__
class RunConfig:
    pitch_deg: float
    rpm: int
    mass_flow: float
    run_id: str # For naming

### Create .pre file editting object
class PreFileEditor:
    """
    Uses placeholder varaibles to edit .pre file:
        __PITCH_DEG__
        __RPM__
        __MASS_FLOW__
    Note that pitch degree is just for maarking/naming the file
    """
    def edit_pre(self, pre_path: Path, cfg: RunConfig) -> None:
        # Inputs: base_pre.pre file file, configuration object
        # No outputs
        text = pre_path.read_text(encoding="utf-8", errors="ignore")
        text = ( # Method chain for simplicity
            text.replace("__PITCH_DEG__", f"{cfg.pitch_deg}")
                .replace("__RPM__", f"{cfg.rpm}")
                .replace("__MASS_FLOW__", f"{cfg.mass_flow}")
        )
        pre_path.write_text(text, encoding="utf-8")

### Create batch run object
class BatchRunner:
    """
    Run batch file created for individual CFD run in working directory
    Save results to log_path directory
    Return 0 if ran without errors
    """
    def __init__(self, bat_path: Path):
        self.bat_path = bat_path

    def run(self, workdir: Path, log_path: Path) -> int:
        proc = subprocess.run(
            ["cmd.exe", "/c", str(self.bat_path)], # Use cmd to ensure runs .bat correct on windows
            cwd = str(workdir), # Give subprocess the working directory location
            capture_output = True,
            text=True # Give stdout,stderr as strings not bytes
        )

        # Create log header/info (from chat)
        log_text = []
        log_text.append(f"=== RUN START: {datetime.now().isoformat()} ===\n")
        log_text.append(f"Workdir: {workdir}\n")
        log_text.append(f"Batch: {self.bat_path}\n")
        log_text.append(f"Return code: {proc.returncode}\n\n")
        log_text.append("=== STDOUT ===\n")
        log_text.append(proc.stdout or "")
        log_text.append("\n=== STDERR ===\n")
        log_text.append(proc.stderr or "")
        log_text.append(f"\n=== RUN END: {datetime.now().isoformat()} ===\n")

        # Write log file or overwrite previous
        log_path.write_text("".join(log_text), encoding="utf-8")
        return proc.returncode


# Create case manager object
class CaseManager:
    def __init__(self, base_case_dir: Path, results_root: Path, pre_relative_path: Path):
        self.base_case_dir



def run_matlab_pitch(matlab_exe: Path, pitch_deg: float, workdir: Path) -> int:
    cmd = (
        f"try, apply_pitch({pitch_deg}); "
        f"catch ME, disp(getReport(ME,'extended')); exit(1); end; exit(0);"
    )

    proc = subprocess.run(
        [str(matlab_exe), "-batch", cmd],
        cwd=str(workdir), # Set workdir to "C:\Users\kagan\Documents\GitHub\Change_Blade_Pitch"
        capture_output=True,
        text=True
    )

    # Write matlab log file to "...\GitHub\Change_Blade_Pitch" location
    (workdir / "matlab.log").write_text(
        f"Return code: {proc.returncode}\n\n"
        f"STDOUT:\n{proc.stdout}\n\n"
        f"STDERR:\n{proc.stderr}",
        encoding="utf-8"
    )
    return proc.returncode















# ----------------------------
# 4) Case manager (folders, copying, metadata)
# ----------------------------
class CaseManager:
    def __init__(
        self,
        base_case_dir: Path,     # contains base .pre, base curves, base scripts, etc.
        results_root: Path,      # where run folders go
        pre_relative_path: Path  # where the .pre lives inside the case folder
    ):
        self.base_case_dir = base_case_dir
        self.results_root = results_root
        self.pre_relative_path = pre_relative_path

    def make_case_folder(self, cfg: RunConfig) -> Path:
        case_dir = self.results_root / cfg.run_id
        if case_dir.exists():
            shutil.rmtree(case_dir)
        shutil.copytree(self.base_case_dir, case_dir)
        return case_dir

    def save_metadata(self, case_dir: Path, cfg: RunConfig) -> None:
        (case_dir / "run_config.json").write_text(
            json.dumps(asdict(cfg), indent=2),
            encoding="utf-8"
        )


# ----------------------------
# 5) Driver: generate 20 runs
# ----------------------------
def build_run_id(pitch_deg: float, rpm: int, mass_flow: float) -> str:
    # Folder-safe ID
    return f"pitch{pitch_deg:0.0f}_rpm{rpm}_mdot{mass_flow:.4f}"


def main():
    # Your ranges
    pitch_array = [0, 2, 4, 6]
    RPM_array = [9000, 10000, 12500, 15000, 17500]
    mass_flow_array = [0.2232, 0.2480, 0.3100, 0.3720, 0.4340]

    # Make sure RPM -> mass_flow mapping stays aligned by index
    rpm_to_mdot = dict(zip(RPM_array, mass_flow_array))

    # Paths (edit these to your project)
    base_case_dir = Path(r"C:\path\to\base_case")          # template folder
    results_root = Path(r"C:\path\to\results\mc_runs")     # output folder
    results_root.mkdir(parents=True, exist_ok=True)

    pre_rel = Path("CFX") / "case.pre"  # example: base_case\CFX\case.pre
    bat_path = Path(r"C:\path\to\run_pipeline.bat")        # your batch pipeline

    manager = CaseManager(base_case_dir, results_root, pre_rel)
    editor = PreFileEditor(use_placeholders=True)
    runner = BatchRunner(bat_path)

    # Generate configs (4 * 5 = 20)
    configs: list[RunConfig] = []
    for pitch in pitch_array:
        for rpm in RPM_array:
            mdot = rpm_to_mdot[rpm]
            run_id = build_run_id(pitch, rpm, mdot)
            configs.append(RunConfig(pitch_deg=pitch, rpm=rpm, mass_flow=mdot, run_id=run_id))

    # Execute
    for i, cfg in enumerate(configs, start=1):
        print(f"[{i}/{len(configs)}] Running {cfg.run_id}")

        case_dir = manager.make_case_folder(cfg)

        src_pre = case_dir / pre_rel  # after copytree, base pre is here
        dst_pre = case_dir / pre_rel  # overwrite in place

        manager.save_metadata(case_dir, cfg)
        editor.edit_pre(src_pre, dst_pre, cfg)

        log_path = case_dir / "run.log"
        rc = runner.run(workdir=case_dir, log_path=log_path)

        # Optional: stop on failure
        if rc != 0:
            print(f"  ERROR: batch returned {rc}. See log: {log_path}")
            break

    print("Done.")


if __name__ == "__main__":
    main()
