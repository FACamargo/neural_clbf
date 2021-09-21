<div align="center">    
 
# Nonlinear Control Using Neural Lyapunov-Barrier Functions

[![Conference](https://img.shields.io/badge/CoRL-Accepted-success)](https://openreview.net/forum?id=8K5kisAnb_p)
   
[![Arxiv](http://img.shields.io/badge/arxiv-eess.sy:2109.06697-B31B1B.svg)](https://www.nature.com/articles/nature14539)

<!--  
Conference   
-->   
</div>
 
## Description
This repository contains our code for learning robust Lyapunov-style control certificates for safety and stability for nonlinear dynamical systems.

## How to run
First, install dependencies   
```bash
# clone project   
git clone https://github.com/dawsonc/neural_clbf

# install project   
cd neural_clbf
conda create --name neural_clbf python=3.9
conda activate neural_clbf
pip install -e .   
pip install -r requirements.txt
```

Once installed, training examples can be run using e.g. `python neural_clbf/training/train_single_track_car.py`, and pre-trained models can be evaluated using the scripts in the `neural_clbf/evaluation` directory. To run training on a remote server with port forwarding for TensorBoard, connect using `ssh -L 16006:127.0.0.1:6006 cbd@realm-01.mit.edu`

### External dependencies

#### F16 Model
To install the F16 simulator (which is a GPL-licensed component and thus not distributed along with this code), you should also run
```
cd ..  # or wherever you want to put it
git clone git@github.com:dawsonc/AeroBenchVVPython.git
cd AeroBenchVVPython
pwd
```
Then go to `neural_clbf/setup/aerobench.py` and modify it to point to the path to the aerobench package.

#### MATLAB Bridge for Robust MPC

```
cd "matlabroot/extern/engines/python"
python setup.py install
```


### Citation
```
@article{dawson_neural_clbf_2021,
  title={Safe Nonlinear Control Using Robust Neural Lyapunov-Barrier Functions},
  author={Charles Dawson, Zengyi Qin, Sicun Gao, Chuchu Fan},
  journal={5th Annual Conference on Robot Learning},
  year={2021}
}
```   
