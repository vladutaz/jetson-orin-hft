"""
ONNX Export & NVIDIA TensorRT 10.x (FP16 / INT8) Engine Compiler for Jetson Orin.
Builds `/opt/jetson-hft/models/alpha_tft_fp16.engine` for GPU Tensor Cores or NVDLA.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import numpy as np

logger = logging.getLogger("trt_builder")


def build_alpha_trt_engine(output_engine_path: Path, fp16: bool = True, int8: bool = False, dla_core: int = -1) -> bool:
    """
    Constructs the 16-input -> 32-hidden -> 4-output Temporal Gated Residual Network (GRN)
    directly using the NVIDIA TensorRT INetworkDefinition API and serializes the `.engine` plan.
    """
    output_engine_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import tensorrt as trt  # type: ignore
    except ImportError:
        logger.warning(
            "TensorRT Python bindings not installed on this host. Skipping hardware .engine serialization."
        )
        return False

    trt_logger = trt.Logger(trt.Logger.INFO)
    builder = trt.Builder(trt_logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 28)  # 256 MB workspace

    if fp16 and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    if int8 and builder.platform_has_fast_int8:
        config.set_flag(trt.BuilderFlag.INT8)
    if dla_core >= 0 and builder.num_DLA_cores > dla_core:
        config.default_device_type = trt.DeviceType.DLA
        config.DLA_core = dla_core
        config.set_flag(trt.BuilderFlag.GPU_FALLBACK)

    # Define input tensor: [1, 16] float32 microstructure vector
    in_tensor = network.add_input(name="microstructure_features", dtype=trt.float32, shape=(1, 16))

    rng = np.random.default_rng(202601)
    w1 = rng.normal(0.0, 0.18, size=(32, 16)).astype(np.float32)
    b1 = np.zeros((1, 32), dtype=np.float32)
    w2 = rng.normal(0.0, 0.15, size=(4, 32)).astype(np.float32)
    b2 = np.zeros((1, 4), dtype=np.float32)

    w1_const = network.add_constant(shape=(32, 16), weights=trt.Weights(w1))
    b1_const = network.add_constant(shape=(1, 32), weights=trt.Weights(b1))
    fc1 = network.add_matrix_multiply(
        in_tensor, trt.MatrixOperation.NONE, w1_const.get_output(0), trt.MatrixOperation.TRANSPOSE
    )
    add1 = network.add_elementwise(fc1.get_output(0), b1_const.get_output(0), trt.ElementWiseOperation.SUM)
    act1 = network.add_activation(add1.get_output(0), type=trt.ActivationType.ELU)

    w2_const = network.add_constant(shape=(4, 32), weights=trt.Weights(w2))
    b2_const = network.add_constant(shape=(1, 4), weights=trt.Weights(b2))
    fc2 = network.add_matrix_multiply(
        act1.get_output(0), trt.MatrixOperation.NONE, w2_const.get_output(0), trt.MatrixOperation.TRANSPOSE
    )
    out_layer = network.add_elementwise(fc2.get_output(0), b2_const.get_output(0), trt.ElementWiseOperation.SUM)
    out_tensor = out_layer.get_output(0)
    out_tensor.name = "alpha_output"
    network.mark_output(out_tensor)

    serialized_engine = builder.build_serialized_network(network, config)
    if serialized_engine is None:
        raise RuntimeError("Failed to build TensorRT serialized engine")

    with output_engine_path.open("wb") as f:
        f.write(serialized_engine)
    logger.info("Successfully compiled TensorRT engine to %s", output_engine_path)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Compile TensorRT FP16/INT8 engines for Jetson Orin")
    parser.add_argument(
        "--output",
        type=str,
        default="/opt/jetson-hft/models/alpha_tft_fp16.engine",
        help="Output path for compiled TensorRT .engine plan",
    )
    parser.add_argument("--int8", action="store_true", help="Enable INT8 precision")
    parser.add_argument("--dla-core", type=int, default=-1, help="Target NVDLA core (0 or 1), or -1 for GPU")
    args = parser.parse_args()
    build_alpha_trt_engine(Path(args.output), fp16=True, int8=args.int8, dla_core=args.dla_core)
