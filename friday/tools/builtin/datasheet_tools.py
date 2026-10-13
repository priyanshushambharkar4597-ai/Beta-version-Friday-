"""Component & Datasheet Spec Lookup Tool - ENTC Hardware Suite for Friday."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from friday.tools.base import BaseTool, PermissionTier

# Curated offline database of core ENTC engineering components
ENTC_COMPONENT_CATALOG: Dict[str, Dict[str, Any]] = {
    "ne555": {
        "name": "NE555 Precision Timer IC",
        "category": "Analog / Timing IC",
        "supply_voltage": "4.5V to 16V",
        "max_current": "200 mA source/sink",
        "logic_family": "Bipolar / CMOS (LMC555)",
        "package": "DIP-8 / SOIC-8",
        "pinout": (
            "1: GND, 2: Trigger (Active Low), 3: Output, 4: Reset (Active Low), "
            "5: Control Voltage (0.01μF to GND), 6: Threshold, 7: Discharge, 8: VCC"
        ),
        "key_parameters": {
            "max_frequency": "500 kHz (Bipolar), 2 MHz (CMOS)",
            "timing_accuracy": "1% typical",
            "threshold_voltage": "2/3 VCC",
            "trigger_voltage": "1/3 VCC",
        },
        "typical_applications": "Monostable pulse generation, astable oscillator, PWM driver.",
    },
    "lm741": {
        "name": "LM741 General Purpose Operational Amplifier",
        "category": "Analog Linear IC",
        "supply_voltage": "±5V to ±18V (Dual Rail, ±15V typical)",
        "max_current": "25 mA short circuit",
        "logic_family": "Bipolar Analog",
        "package": "DIP-8 / TO-99",
        "pinout": (
            "1: Offset Null, 2: Inverting Input (-), 3: Non-Inverting Input (+), "
            "4: V- (Negative Rail), 5: Offset Null, 6: Output, 7: V+ (Positive Rail), 8: NC"
        ),
        "key_parameters": {
            "gain_bandwidth_product": "1.0 MHz",
            "slew_rate": "0.5 V/μs",
            "input_impedance": "2 MΩ",
            "input_offset_voltage": "1 mV to 5 mV",
        },
        "typical_applications": "Inverting/non-inverting amplifiers, active filters, comparators.",
    },
    "lm358": {
        "name": "LM358 Dual Low-Power Operational Amplifier",
        "category": "Analog Linear IC",
        "supply_voltage": "3.0V to 32V (Single Supply) or ±1.5V to ±16V (Dual)",
        "max_current": "40 mA sink / 20 mA source",
        "logic_family": "Bipolar Analog",
        "package": "DIP-8 / SOIC-8",
        "pinout": (
            "1: Out 1, 2: In1-, 3: In1+, 4: GND/V-, 5: In2+, 6: In2-, 7: Out 2, 8: VCC/V+"
        ),
        "key_parameters": {
            "gain_bandwidth_product": "1.0 MHz",
            "slew_rate": "0.6 V/μs",
            "input_common_mode": "Includes ground (0V to VCC-1.5V)",
            "quiescent_current": "500 μA typical",
        },
        "typical_applications": "Transducer amplifiers, DC gain blocks, single-supply sensor interfaces.",
    },
    "esp32": {
        "name": "ESP32-WROOM-32 Wi-Fi & BLE Microcontroller",
        "category": "Embedded Microcontroller & IoT SoC",
        "supply_voltage": "3.0V to 3.6V (3.3V typical)",
        "max_current": "500 mA peak (Wi-Fi Tx), ~80 mA idle",
        "logic_family": "3.3V CMOS (NOT 5V tolerant)",
        "package": "SMD Module / NodeMCU DevKit (30/38 pins)",
        "pinout": (
            "GPIO0 (Boot), GPIO2 (Onboard LED), GPIO1/3 (UART0 TX/RX), "
            "GPIO21/22 (I2C SDA/SCL), GPIO18/19/23 (VSPI SCK/MISO/MOSI), EN (Reset)"
        ),
        "key_parameters": {
            "cpu": "Xtensa Dual-Core 32-bit LX6 @ up to 240 MHz",
            "sram": "520 KB on-chip SRAM",
            "flash": "4 MB external SPI flash",
            "wireless": "Wi-Fi 802.11 b/g/n + Bluetooth 4.2 / BLE",
            "adc": "12-bit SAR ADC up to 18 channels",
            "dac": "Two 8-bit DAC channels",
        },
        "typical_applications": "IoT telemetry, edge sensor nodes, wireless DSP.",
    },
    "atmega328p": {
        "name": "ATmega328P 8-bit AVR Microcontroller",
        "category": "Microcontroller",
        "supply_voltage": "1.8V to 5.5V (5.0V typical on Arduino Uno)",
        "max_current": "40 mA per I/O pin (200 mA total VCC package)",
        "logic_family": "5V CMOS",
        "package": "DIP-28 / TQFP-32",
        "pinout": (
            "Pin 1: RESET, Pin 2/3: RXD/TXD (PD0/PD1), Pin 7: VCC, Pin 8: GND, "
            "Pin 9/10: XTAL1/2, Pin 12-19: PB0-PB5 (SPI MOSI/MISO/SCK), Pin 23-28: PC0-PC5 (ADC0-ADC5, I2C)"
        ),
        "key_parameters": {
            "clock_speed": "Up to 20 MHz (16 MHz standard)",
            "flash_memory": "32 KB",
            "sram": "2 KB",
            "eeprom": "1 KB",
            "timers": "Two 8-bit, one 16-bit timer with PWM",
        },
        "typical_applications": "Arduino Uno, robotics, embedded control, instrumentation.",
    },
    "stm32f103": {
        "name": "STM32F103C8T6 (ARM Cortex-M3 Blue Pill)",
        "category": "Microcontroller",
        "supply_voltage": "2.0V to 3.6V (3.3V typical)",
        "max_current": "25 mA per I/O pin",
        "logic_family": "3.3V CMOS (Certain pins 5V tolerant)",
        "package": "LQFP-48",
        "pinout": (
            "PA9/PA10: USART1 TX/RX, PB6/PB7: I2C1 SCL/SDA, PA5/PA6/PA7: SPI1 SCK/MISO/MOSI, "
            "PA0-PA7: 12-bit ADC channels, PC13: Onboard LED"
        ),
        "key_parameters": {
            "cpu": "ARM 32-bit Cortex-M3 @ 72 MHz",
            "flash": "64 KB / 128 KB",
            "sram": "20 KB",
            "timers": "4 general purpose 16-bit timers with PWM",
            "communication": "2x I2C, 3x USART, 2x SPI, USB 2.0 FS",
        },
        "typical_applications": "Industrial controls, digital filters, motor drivers, robotics.",
    },
    "2n2222": {
        "name": "2N2222 NPN Silicon Bipolar Junction Transistor",
        "category": "Discrete Semiconductor",
        "supply_voltage": "Vceo = 30V, Vcbo = 60V, Vebo = 5V",
        "max_current": "Ic = 800 mA continuous",
        "logic_family": "BJT",
        "package": "TO-92 / TO-18",
        "pinout": "1: Emitter, 2: Base, 3: Collector (Facing flat side, pins down: E-B-C)",
        "key_parameters": {
            "dc_current_gain_hfe": "100 to 300 @ Ic = 150 mA",
            "transition_frequency_ft": "250 MHz to 300 MHz",
            "saturation_voltage_vce_sat": "0.3V @ Ic = 150 mA, Ib = 15 mA",
            "power_dissipation": "625 mW (TO-92)",
        },
        "typical_applications": "Small signal amplification, high-speed saturation switching, relay driving.",
    },
    "1n4007": {
        "name": "1N4007 Standard Recovery Silicon Rectifier Diode",
        "category": "Discrete Semiconductor",
        "supply_voltage": "Peak Repetitive Reverse Voltage (VRRM) = 1000V",
        "max_current": "Forward Current (IF) = 1.0 A continuous, 30A non-repetitive surge",
        "logic_family": "Diode",
        "package": "DO-41 Axial",
        "pinout": "Cathode marked by white/silver band; Anode unmarked terminal.",
        "key_parameters": {
            "forward_voltage_drop_vf": "1.1 V @ 1.0 A",
            "reverse_leakage_current": "5 μA @ 25°C",
            "reverse_recovery_time": "30 μs (Mains rectification, not for high-speed SMPS)",
        },
        "typical_applications": "Full-wave bridge rectifiers, flyback / freewheeling protection across inductive loads.",
    },
    "lm317": {
        "name": "LM317 Adjustable Positive Linear Voltage Regulator",
        "category": "Power Management IC",
        "supply_voltage": "Input up to 40V; Vin - Vout difference = 3V to 40V",
        "max_current": "Output Current (Iout) up to 1.5 A",
        "logic_family": "Linear Regulator",
        "package": "TO-220 / D2PAK",
        "pinout": "Pin 1: Adjust (ADJ), Pin 2: Output (VOUT), Pin 3: Input (VIN). Heat tab is tied to Pin 2.",
        "key_parameters": {
            "output_voltage_range": "1.25 V to 37 V",
            "reference_voltage": "1.25 V between OUT and ADJ",
            "line_regulation": "0.01% typical",
            "load_regulation": "0.1% typical",
            "design_formula": "Vout = 1.25V * (1 + R2/R1) + Iadj * R2 (where R1 = 240 Ω standard)",
        },
        "typical_applications": "Lab bench power supplies, constant current sources, battery chargers.",
    },
}


class SearchDatasheetTool(BaseTool):
    """Tool to search electrical specifications, pinouts, and parameters for ENTC components."""

    name = "search_datasheet"
    description = (
        "Search electrical datasheets and pinout configurations for microcontrollers, "
        "ICs, op-amps, transistors, and diodes. Formats voltage ranges, maximum currents, "
        "logic families, and package pinouts."
    )
    tier = PermissionTier.READ

    def execute(self, component_name: str, **kwargs: Any) -> Dict[str, Any]:
        """Search and format datasheet information for target component."""
        clean_query = re.sub(r"[^a-zA-Z0-9]", "", component_name).lower()

        # Check in local curated catalog
        for key, spec in ENTC_COMPONENT_CATALOG.items():
            if key in clean_query or clean_query in key:
                return {
                    "status": "found",
                    "component": spec["name"],
                    "category": spec["category"],
                    "supply_voltage": spec["supply_voltage"],
                    "max_current": spec["max_current"],
                    "logic_family": spec["logic_family"],
                    "package": spec["package"],
                    "pinout": spec["pinout"],
                    "key_parameters": spec["key_parameters"],
                    "typical_applications": spec["typical_applications"],
                }

        # Fallback summary for non-catalog components
        return {
            "status": "generic_spec_lookup",
            "component": component_name.upper(),
            "notice": f"Component '{component_name}' not in offline pre-cached catalog.",
            "datasheet_archive_url": f"https://www.alldatasheet.com/view.jsp?Searchword={component_name}",
            "octopart_url": f"https://octopart.com/search?q={component_name}",
            "guidance": "Verify max operating voltage, thermal dissipation, and logic thresholds before breadboarding.",
        }
