The technical specifications for the **Intel Arc B580** GPU (Battlemage architecture):

### 🛠️ Architecture & Core Build

* **Architecture:** Xe2-HPG (Battlemage, codename *BMG-G21*)
* **Manufacturing Process:** TSMC N5 (5 nm)
* **Die Size & Transistors:** $272\text{ mm}^2$, 19.6 billion transistors
* **Base / Boost Clock:** ~1.7 GHz base / **2.67 GHz** boost (custom partner cards often factory-overclock higher, e.g., 2.8 GHz)

### ⚙️ Compute & Processing Units

* **Xe Cores:** 20
* **Shading Units (ALUs):** 2,560
* **XMX Engines (AI/Tensor Cores):** 160
* **Ray Tracing Units:** 20
* **TMUs / ROPs:** 160 / 80
* **Theoretical Performance:**
* FP32: ~13.67 TFLOPS
* FP16: ~27.34 TFLOPS



### 🧠 Memory Subsystem

* **Capacity:** **12 GB GDDR6**
* **Memory Bus Width:** 192-bit
* **Memory Speed:** 19 Gbps effective
* **Memory Bandwidth:** **456 GB/s**

### ⚡ Power, Interface & Form Factor

* **Bus Interface:** PCIe 4.0 x8
* **TDP / Power Consumption:** 190 W
* **Power Connectors:** Typically 2x 8-pin (varies by board partner)

### 🖥️ Connectivity & Features

* **Display Outputs:** DisplayPort 2.1 (supporting up to UHBR13.5), HDMI 2.1a
* **Media Engine:** Full hardware acceleration for AV1, HEVC, and H.264 (dual-encode capability)
* **API Support:** DirectX 12 Ultimate, Vulkan 1.4, OpenGL 4.6, OpenCL 3.0
* **Technologies:** Intel XeSS (Xe Super Sampling) with frame generation support, hardware XMX matrix acceleration for local AI inference workloads.
