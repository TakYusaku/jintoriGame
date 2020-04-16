FROM nvidia/cuda:9.0-cudnn7-devel-ubuntu16.04

ENV ML_SOURCE /aws/ml_models/
WORKDIR $ML_SOURCE

ARG PYTHON_VERSION=3.6
# golang added
RUN apt-get update && apt-get install -y --no-install-recommends \
         golang \
         build-essential \
         cmake \
         git \
         curl \
         ca-certificates \
         libjpeg-dev \
         libpng-dev && \
     rm -rf /var/lib/apt/lists/*

RUN curl -o ~/miniconda.sh -O  https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh  && \
     chmod +x ~/miniconda.sh && \
     ~/miniconda.sh -b -p /opt/conda && \
     rm ~/miniconda.sh && \
     /opt/conda/bin/conda install -y python=$PYTHON_VERSION numpy pyyaml scipy ipython mkl mkl-include ninja cython typing && \
     /opt/conda/bin/conda install pytorch=0.4.1 cuda90 -c pytorch && \
     /opt/conda/bin/conda clean -ya
ENV PATH /opt/conda/bin:$PATH

WORKDIR /opt/pytorch

# COPY . .
COPY requirements.txt .

RUN pip install -r requirements.txt

RUN TORCH_CUDA_ARCH_LIST="3.5 5.2 6.0 6.1 7.0+PTX" TORCH_NVCC_FLAGS="-Xfatbin -compress-all" \
    CMAKE_PREFIX_PATH="$(dirname $(which conda))/../"

WORKDIR /workspace
RUN chmod -R a+w .

ENV PYTHONPATH "${PYTHONPATH}:/workspace"

ADD batchjob.sh .
RUN chmod +x batchjob.sh
