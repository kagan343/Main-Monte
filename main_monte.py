
from __future__ import annotations

import os
import csv
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

# Ranges of pitch changes (only positive for now, need to fix bug in matlab code)
pitch_array = [0]

# Ranges for RPM and Mass flow rate (from excel calcs)
# for now having RPM dicated what mass flow rate would be
# RPM_array = [10000, 10500, 11000, 11500, 12000, 12500, 15000, 17500]
# mass_flow_array = [0.2478, 0.2604, 0.2728, 0.2852, 0.2976, 0.3099, 0.3720, 0.4340]
RPM_array = [9549, 10931]
mass_flow_array = [0.2368, 0.2711]

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
    def edit_pre(self, template_path: Path, output_pre_path: Path, cfg: RunConfig) -> None:
        # Inputs: TEMPLATE_base_pre.pre file file, configuration object
        # No outputs in python, but writes copy of editted file to base_pre.pre
        text = template_pre_path.read_text(encoding="utf-8", errors="ignore")
        text = ( # Method chain for simplicity
            text.replace("__PITCH_DEG__", f"{cfg.pitch_deg}")
                .replace("__RPM__", f"{cfg.rpm}")
                .replace("__MASS_FLOW__", f"{cfg.mass_flow}")
        )
        output_pre_path.write_text(text, encoding="utf-8")


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

        print("successfully ran proc line, attempting log text")
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
    def __init__(
            self,
            results_root: Path, # Folder where monte run results are stored, passed in by user
            solver_workdir: Path, # will be hard path of ...\temp_results_folder
            out_filename: str, # will be temp_results.out
            res_filename: str, # will be temp_results.res
            txt_filename: str, # will be temp_report.txt
            photo_dir_name: str, # will be temp_report (folder)
            csv_path: Path, # Not sure yet
    ):
        self.results_root = results_root
        if not self.results_root.exists():
            raise FileNotFoundError(f"results_roots does not exist: {self.results_root}")
        if not self.results_root.is_dir():
            raise NotADirectoryError(f"results_root is not a directory: {self.results_root}")
                                    
        self.solver_workdir = solver_workdir
        self.out_filename = out_filename
        self.res_filename = res_filename
        self.txt_filename = txt_filename
        self.photo_dir_name = photo_dir_name
        self.csv_path = csv_path

    def dest_out_path(self, cfg: RunConfig) -> Path:
        # Set filename for results storage (.out)
        return self.results_root / f"{cfg.run_id}.out"

    def dest_res_path(self, cfg: RunConfig) -> Path:
        # Set filename for results storage (.res)
        return self.results_root / f"{cfg.run_id}.res"
    
    def dest_txt_path(self, cfg: RunConfig) -> Path:
        # Set filename for results storage (.txt)
        return self.results_root / f"{cfg.run_id}.txt"
    
    def read_pr(self) -> float:
        # Read pressure ratio from report (self.src_txt)
        report_path = self.solver_workdir / self.txt_filename
        print(f"Reading PR from: {report_path}")
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if "Total Pressure Ratio" in line:
                # Grab the first floating number on the line (handles tabs/spaces)
                # Search term below from chat, wasn't sure best way to parse line for number
                m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
                if not m:
                    raise ValueError(f"Found PR label but no number on line: {line!r}")
                return float(m.group(0))

    def append_pr_to_csv(self, cfg: RunConfig, pr: float) -> None:
        # Append PR to new line in .csv file
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([cfg.run_id, pr])
            # Force save/ write to disk incase crash later
            # had to look up, flush pushes python's memory onto os memory, fileno just forces a write to disk
            f.flush()
            os.fsync(f.fileno())

    def collect_outputs(self, cfg: RunConfig) -> tuple[Path, Path]:
        """
        Copies the temp_results.out/.res files from temp_results_folder
        Paste into storage folder for given monte run
        Outputs are two paths, one for updated name .out and one for .res
        """
        print(f"starting outputs")
        # Find src files
        src_out = self.solver_workdir / self.out_filename # Combine paths for .out
        src_res = self.solver_workdir / self.res_filename # Combine paths for .res
        src_txt = self.solver_workdir / self.txt_filename # Combine paths for .txt
        src_dir = self.solver_workdir / self.photo_dir_name # Combine paths for photo dir
        if not src_out.exists() or not src_res.exists():
            raise FileNotFoundError(f".out {src_out} or .res {src_res} not found")
        
        print("attempting to copy files")
        # Set/copy to destination files
        dst_out = self.dest_out_path(cfg)
        dst_res = self.dest_res_path(cfg)
        dst_txt = self.dest_txt_path(cfg)
        shutil.copy2(src_out, dst_out)
        shutil.copy2(src_res, dst_res)
        shutil.copy2(src_txt, dst_txt)
        assert dst_out.exists() and dst_res.exists() and dst_txt.exists(), "Result copy failed"
        print(f"copied to: {dst_out}\n {dst_res}\n {dst_txt}\n")

        # Before deleting from temp folder, read .txt for pressure ratio
        pressure_ratio = self.read_pr()
        self.append_pr_to_csv(cfg, pressure_ratio)

        print("about to delete old temp_results.out/.res and temp_report.txt")
        # The batch script won't override temp_output.out/ .res / .txt so need to 
        # delete it before next run (after copying above)
        # Also delete the photo folder that .cse makes
        if src_out.exists():
            src_out.unlink()
        if src_res.exists():
            src_res.unlink()
        if src_txt.exists():
            src_txt.unlink()
        if src_dir.exists():
            shutil.rmtree(src_dir)
        assert not src_out.exists(), "temp .out file was not deleted"
        assert not src_res.exists(), "temp .res file was not deleted"
        assert not src_txt.exists(), "temp .txt file was not deleted"
        assert not src_dir.exists(), "temp report dir was not deleted"
        print("deleted files")

        return dst_out, dst_res

        


# Create function for running matlab with pitch angle change
def run_matlab_pitch(matlab_exe: Path, pitch_deg: float, workdir: Path) -> int:
    cmd = (
        f"try, main({pitch_deg}); "
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


# Function for creating total run configurations
# will need to update when/if I add more variables
def build_run_configs(
        pitch_array: list[float],
        rpm_array: list[int],
        mass_flow_array: list[float]
) -> list[RunConfig]:
    
    # Mass flow from rpm so connected, check if arrays are equal length
    if len(mass_flow_array) != len(rpm_array):
        raise ValueError(f"mass_flow_array and rpm_array are not the same length")
    
    cfgs: list[RunConfig] = [] # Create empty list to store config objects, use type annotation
    for pitch in pitch_array:
        for rpm, mdot in zip(rpm_array, mass_flow_array):
            run_id = f"p{pitch:g}_rpm{rpm}_mdot{mdot:.4f}".replace(".","p")
            cfgs.append(RunConfig(pitch_deg=pitch, rpm=rpm, mass_flow=mdot, run_id=run_id)) # Add object to list
    return cfgs


# Function for running "monte carlo"
def run_monte(
        cfgs: list[RunConfig], # List of configuration objects
        matlab_exe: Path, # Path to matlab.exe, is "C:\Program Files\MATLAB\R2024a\bin\matlab.exe"
        matlab_workdir: Path, # Path to main.m of pitch change, will be C:\Users\kagan\Documents\GitHub\Change_Blade_Pitch\main.m
        template_pre_path: Path, # Path to TEMPLATE_base_pre.pre, "C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run\base_pre.pre"
        output_pre_path: Path, # Path to base_pre.pre as output
        batch_workdir: Path, # C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run
        batch_file: Path, # "C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run\single_run.bat"
        case_manager: CaseManager, # case manager object
) -> None:
    pre_editor = PreFileEditor() # Initialize pre editor object
    runner = BatchRunner(batch_file) # Initialize batch runner object with .bat file

    for i, cfg in enumerate(cfgs, start=1):
        print(f"\nCASE {i}/{len(cfgs)}: {cfg.run_id}")

        # 1) Run matlab script for pitch
        """
        Might want to edit matlab script to check if files already made, but runs pretty fast for now
        """
        m_run = run_matlab_pitch(matlab_exe, cfg.pitch_deg, matlab_workdir)
        if m_run != 0:
            raise RuntimeError(f"Matlab failed for {cfg.run_id} (return code {m_run})")
        print(f"Completed matlab run of {matlab_workdir}")

        # 2) Edit .pre file (rpm and mdot)
        pre_editor.edit_pre(template_pre_path, output_pre_path, cfg)
        print(f"Completed edit of {template_pre_path}, wrote to {output_pre_path}")

        # 3) Run solver using single_run.bat
        log_path = case_manager.results_root / f"{cfg.run_id}_solve.log" # Create file for log
        batch_run = runner.run(batch_workdir, log_path)
        if batch_run != 0:
            raise RuntimeError(f"Solver batch failed for {cfg.run_id} (return code {batch_run})")
        
        # 4) Collect results
        out_path, res_path = case_manager.collect_outputs(cfg)
        print(f"Saved: {out_path.name}, {res_path.name}") # Name is inherent property to path

        # 5) Write to excel (atleast pressure ratio)

def make_csv_headers(csv_path: Path):
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["run_id", "pressure_ratio"])



if __name__ == "__main__":

    ### USER INPUT ###
    # Ensure temp_results folder is empty before running, will delete during run
    # but not by itself during the 1st iteration, need to update this
    results_folder_name = "testing_12-29-2025" # Ex. monte_12-26-2025

    # Build configurations array
    cfgs = build_run_configs(pitch_array, RPM_array, mass_flow_array)

    # FIXED PATHS (for now)
    matlab_exe = Path(r"C:\Program Files\MATLAB\R2024a\bin\matlab.exe")
    matlab_workdir = Path(r"C:\Users\kagan\Documents\GitHub\Change_Blade_Pitch")

    template_pre_path = Path(r"C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run\TEMPLATE_base_pre.pre")
    output_pre_path = Path(r"C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run\base_pre.pre")
    batch_workdir = Path(r"C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run")
    batch_file = Path(r"C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run\single_run.bat")

    results_root = (Path(r"C:\Users\kagan\Documents\GitHub\Main-Monte\RESULTS_STORAGE") / results_folder_name)
    results_root.mkdir(parents=True, exist_ok=True)

    temp_results_folder = Path(r"C:\Users\kagan\Desktop_v2\Projects-Tutorials\Minature TurboJet\Prototype_v2\ANSYS\Batch Run\temp_results_folder")

    csv_path = (Path(r"C:\Users\kagan\Documents\GitHub\Main-Monte\RESULTS_STORAGE") / results_folder_name / "results.csv")
    make_csv_headers(csv_path)

    case_mgr = CaseManager(
        results_root=results_root,
        solver_workdir=temp_results_folder,
        out_filename="temp_results.out",
        res_filename="temp_results.res",
        txt_filename="temp_report.txt",
        photo_dir_name="temp_report",
        csv_path=csv_path,
    )

    run_monte(
        cfgs=cfgs,
        matlab_exe=matlab_exe,
        matlab_workdir=matlab_workdir,
        template_pre_path=template_pre_path,
        output_pre_path=output_pre_path,
        batch_workdir=batch_workdir,
        batch_file=batch_file,
        case_manager=case_mgr,
    )















# if __name__ == "__main__":
#     test_pre = Path(r"C:\Users\kagan\Documents\GitHub\Main-Monte\testing\TESTbase_pre.pre")
#     test_cfg = RunConfig(
#         pitch_deg=5,
#         rpm=12500,
#         mass_flow=0.31,
#         run_id="TEST"
#     )
    
#     editor = PreFileEditor(); # Create editor class
#     editor.edit_pre(test_pre, test_cfg)

