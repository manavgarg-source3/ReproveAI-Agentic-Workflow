FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

# Trusted, prebuilt dependency layer for the Hamiltonian Neural Networks
# reproduction target. The experiment itself is mounted read-only at runtime.
RUN python -m pip install --no-cache-dir \
    autograd==1.8.0 \
    imageio==2.37.0 \
    numpy==1.26.4 \
    scipy==1.16.3 \
    torch==2.9.0
