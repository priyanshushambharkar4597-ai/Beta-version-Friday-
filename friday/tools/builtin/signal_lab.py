"""Signal Analysis & Filter Workbench - ENTC Hardware & Signal Suite for Friday."""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend to prevent GUI thread hangs
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from friday.tools.base import BaseTool, PermissionTier


class AnalyzeTransferFunctionTool(BaseTool):
    """Tool to analyze linear time-invariant (LTI) transfer functions and generate plots."""

    name = "analyze_transfer_function"
    description = (
        "Analyze an analog transfer function H(s) = num(s)/den(s). Calculates poles, "
        "zeros, stability, and cutoff frequency (-3dB). Generates Bode, Nyquist, or "
        "step response plots embedded into Obsidian vault attachments."
    )
    tier = PermissionTier.REVERSIBLE

    def __init__(self, attachments_dir: Optional[str] = None) -> None:
        """Initialize AnalyzeTransferFunctionTool.

        Args:
            attachments_dir: Directory where plot PNGs are saved. Defaults to ./vault/attachments.
        """
        if attachments_dir is None:
            default_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "vault", "attachments")
            )
            self.attachments_dir = Path(default_dir)
        else:
            self.attachments_dir = Path(os.path.abspath(attachments_dir))

        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        num: List[float],
        den: List[float],
        plot_type: str = "bode",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Analyze transfer function and generate requested plot."""
        if not num or not den:
            raise ValueError("Numerator and denominator polynomial coefficients must be non-empty.")

        # Create continuous-time LTI system
        sys_lti = signal.TransferFunction(num, den)

        # Poles and zeros
        poles = [complex(p) for p in sys_lti.poles]
        zeros = [complex(z) for z in sys_lti.zeros]

        # Stability verdict
        real_parts = [p.real for p in poles]
        if all(r < -1e-9 for r in real_parts):
            stability = "STABLE (All poles in open left-half complex plane)"
        elif any(r > 1e-9 for r in real_parts):
            stability = "UNSTABLE (Pole(s) detected in right-half complex plane)"
        else:
            stability = "MARGINALLY STABLE (Pole(s) on imaginary axis)"

        # Generate unique filename for plot
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        plot_type_clean = plot_type.strip().lower()
        filename = f"tf_{plot_type_clean}_{ts}.png"
        plot_path = self.attachments_dir / filename

        # Compute cutoff frequency (-3dB)
        w, mag, phase = signal.bode(sys_lti, n=500)
        max_mag = float(np.max(mag))
        cutoff_idx = int(np.argmin(np.abs(mag - (max_mag - 3.01))))
        cutoff_rad_s = float(w[cutoff_idx])
        cutoff_hz = float(cutoff_rad_s / (2 * math.pi))

        # Generate requested visualization
        fig = plt.figure(figsize=(9, 5), dpi=100)
        plt.style.use("dark_background")

        if plot_type_clean == "bode":
            ax1 = fig.add_subplot(2, 1, 1)
            ax1.semilogx(w / (2 * math.pi), mag, color="#00ffff", lw=2)
            ax1.axhline(max_mag - 3.01, color="#ffaa00", ls="--", label="-3dB Cutoff")
            ax1.set_ylabel("Magnitude (dB)", color="#ffffff")
            ax1.set_title("Bode Frequency Response", color="#00ffff", fontsize=11)
            ax1.grid(True, which="both", color="#333333", linestyle=":")
            ax1.legend(loc="best")

            ax2 = fig.add_subplot(2, 1, 2)
            ax2.semilogx(w / (2 * math.pi), phase, color="#ff0077", lw=2)
            ax2.set_xlabel("Frequency (Hz)", color="#ffffff")
            ax2.set_ylabel("Phase (deg)", color="#ffffff")
            ax2.grid(True, which="both", color="#333333", linestyle=":")

        elif plot_type_clean == "nyquist":
            # Frequency vector for Nyquist
            w_nyq, h_nyq = signal.freqresp(sys_lti)
            ax = fig.add_subplot(1, 1, 1)
            ax.plot(h_nyq.real, h_nyq.imag, color="#00ffff", lw=2, label="H(jω)")
            ax.plot(h_nyq.real, -h_nyq.imag, color="#00ffff", ls="--", lw=1, alpha=0.6)
            ax.plot([-1], [0], "ro", label="Critical Point (-1, 0)")
            ax.set_xlabel("Real", color="#ffffff")
            ax.set_ylabel("Imaginary", color="#ffffff")
            ax.set_title("Nyquist Stability Diagram", color="#00ffff", fontsize=11)
            ax.grid(True, color="#333333", linestyle=":")
            ax.legend(loc="best")

        elif plot_type_clean == "step":
            t, y = signal.step(sys_lti)
            ax = fig.add_subplot(1, 1, 1)
            ax.plot(t, y, color="#00ffff", lw=2)
            ax.set_xlabel("Time (s)", color="#ffffff")
            ax.set_ylabel("Amplitude", color="#ffffff")
            ax.set_title("Transient Step Response", color="#00ffff", fontsize=11)
            ax.grid(True, color="#333333", linestyle=":")

        else:
            plt.close(fig)
            raise ValueError(f"Unsupported plot_type '{plot_type}'. Choose 'bode', 'nyquist', or 'step'.")

        fig.tight_layout()
        fig.savefig(plot_path, format="png", bbox_inches="tight")
        plt.close(fig)

        return {
            "status": "success",
            "stability": stability,
            "poles": [f"{p.real:.4f} + {p.imag:.4f}j" for p in poles],
            "zeros": [f"{z.real:.4f} + {z.imag:.4f}j" for z in zeros],
            "cutoff_rad_s": round(cutoff_rad_s, 2),
            "cutoff_hz": round(cutoff_hz, 2),
            "plot_type": plot_type_clean,
            "plot_path": str(plot_path),
            "markdown_embed": f"![[{filename}]]",
        }


class DesignAnalogFilterTool(BaseTool):
    """Tool to design analog filters and calculate standard resistor/capacitor components."""

    name = "design_analog_filter"
    description = (
        "Design analog active/passive filters (Butterworth, Chebyshev, Bessel). "
        "Computes transfer function coefficients, pole locations, and component "
        "sizing guidance (e.g. Sallen-Key topology)."
    )
    tier = PermissionTier.REVERSIBLE

    def execute(
        self,
        filter_type: str = "butterworth",
        response: str = "lowpass",
        order: int = 2,
        cutoff_hz: Union[float, List[float]] = 1000.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Design active analog filter with given specifications."""
        ftype = filter_type.strip().lower()
        btype = response.strip().lower()

        # Normalize cutoff frequency to rad/s for analog synthesis
        if isinstance(cutoff_hz, (list, tuple)):
            Wn = [2 * math.pi * float(f) for f in cutoff_hz]
            fc_display = [float(f) for f in cutoff_hz]
        else:
            Wn = 2 * math.pi * float(cutoff_hz)
            fc_display = float(cutoff_hz)

        # Synthesize transfer function polynomials
        if "butter" in ftype:
            b, a = signal.butter(order, Wn, btype=btype, analog=True)
            filter_name = "Butterworth (Maximally Flat)"
        elif "cheby" in ftype:
            b, a = signal.cheby1(order, rp=1.0, Wn=Wn, btype=btype, analog=True)
            filter_name = "Chebyshev Type I (1.0 dB Ripple)"
        elif "bessel" in ftype:
            b, a = signal.bessel(order, Wn, btype=btype, analog=True)
            filter_name = "Bessel-Thomson (Linear Phase)"
        else:
            raise ValueError(f"Unsupported filter_type '{filter_type}'. Choose 'butterworth', 'chebyshev', or 'bessel'.")

        num = [float(x) for x in b]
        den = [float(x) for x in a]

        # Calculate component guidance for Sallen-Key 2nd-order active stage
        fc_val = fc_display if isinstance(fc_display, float) else fc_display[0]
        c_val = 10e-9  # standard 10 nF capacitor
        r_val = 1.0 / (2 * math.pi * fc_val * c_val) if fc_val > 0 else 0

        guidance = (
            f"Active Sallen-Key Stage Implementation Guidance:\n"
            f"- For 2nd-order Low-pass with unity gain:\n"
            f"  * Select C1 = C2 = 10 nF (standard ceramic/polyester)\n"
            f"  * Target Resistor R1 = R2 = {r_val/1000:.2f} kΩ (Standard E24 nearest resistor)\n"
            f"- Recommended Op-Amp: OPA1612 / TL072 for audio, LM358 for DC control."
        )

        return {
            "status": "designed",
            "filter_name": filter_name,
            "response": btype,
            "order": order,
            "cutoff_hz": fc_display,
            "numerator": num,
            "denominator": den,
            "component_guidance": guidance,
        }
