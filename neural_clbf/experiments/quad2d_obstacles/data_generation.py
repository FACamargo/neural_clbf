"""File for generating training data for the Quad2D obstacle avoidance experiment"""
from typing import List, Optional, Tuple

import numpy as np
import torch
import pytorch_lightning as pl
from torch.utils.data import TensorDataset, DataLoader

from neural_clbf.systems.quad2d import Quad2D


def safe_mask_fn(x):
    """Return the mask of x indicating safe regions for the obstacle task"""
    safe_mask = torch.ones_like(x[:, 0], dtype=torch.bool)

    # We have a floor that we need to avoid
    safe_z = -0.1
    floor_mask = x[:, 1] >= safe_z
    safe_mask.logical_and_(floor_mask)

    # We also have a block obstacle to the left at ground level
    obs1_min_x, obs1_max_x = (-1.1, -0.4)
    obs1_min_z, obs1_max_z = (-0.5, 0.6)
    obs1_mask_x = torch.logical_or(x[:, 0] <= obs1_min_x, x[:, 0] >= obs1_max_x)
    obs1_mask_z = torch.logical_or(x[:, 1] <= obs1_min_z, x[:, 1] >= obs1_max_z)
    obs1_mask = torch.logical_or(obs1_mask_x, obs1_mask_z)
    safe_mask.logical_and_(obs1_mask)

    # We also have a block obstacle to the right in the air
    obs2_min_x, obs2_max_x = (-0.1, 1.1)
    obs2_min_z, obs2_max_z = (0.7, 1.5)
    obs2_mask_x = torch.logical_or(x[:, 0] <= obs2_min_x, x[:, 0] >= obs2_max_x)
    obs2_mask_z = torch.logical_or(x[:, 1] <= obs2_min_z, x[:, 1] >= obs2_max_z)
    obs2_mask = torch.logical_or(obs2_mask_x, obs2_mask_z)
    safe_mask.logical_and_(obs2_mask)

    # Also constrain to be within a norm bound
    norm_mask = x.norm(dim=-1) <= 4.5
    safe_mask.logical_and_(norm_mask)

    return safe_mask


def unsafe_mask_fn(x):
    """Return the mask of x indicating unsafe regions for the obstacle task"""
    unsafe_mask = torch.zeros_like(x[:, 0], dtype=torch.bool)

    # We have a floor that we need to avoid
    unsafe_z = -0.3
    floor_mask = x[:, 1] <= unsafe_z
    unsafe_mask.logical_or_(floor_mask)

    # We also have a block obstacle to the left at ground level
    obs1_min_x, obs1_max_x = (-1.0, -0.5)
    obs1_min_z, obs1_max_z = (-0.4, 0.5)
    obs1_mask_x = torch.logical_and(x[:, 0] >= obs1_min_x, x[:, 0] <= obs1_max_x)
    obs1_mask_z = torch.logical_and(x[:, 1] >= obs1_min_z, x[:, 1] <= obs1_max_z)
    obs1_mask = torch.logical_and(obs1_mask_x, obs1_mask_z)
    unsafe_mask.logical_or_(obs1_mask)

    # We also have a block obstacle to the right in the air
    obs2_min_x, obs2_max_x = (0.0, 1.0)
    obs2_min_z, obs2_max_z = (0.8, 1.4)
    obs2_mask_x = torch.logical_and(x[:, 0] >= obs2_min_x, x[:, 0] <= obs2_max_x)
    obs2_mask_z = torch.logical_and(x[:, 1] >= obs2_min_z, x[:, 1] <= obs2_max_z)
    obs2_mask = torch.logical_and(obs2_mask_x, obs2_mask_z)
    unsafe_mask.logical_or_(obs2_mask)

    # Also constrain with a norm bound
    norm_mask = x.norm(dim=-1) >= 5.0
    unsafe_mask.logical_or_(norm_mask)

    return unsafe_mask


class Quad2DObstaclesDataModule(pl.LightningDataModule):
    """
    DataModule for generating sample points (and a corresponding safe/unsafe mask) for
    the 2D quadrotor obstacle avoidance experiment.
    """

    def __init__(
        self,
        N_samples: int = 1000000,
        domains: Optional[List[List[Tuple[float, float]]]] = None,
        split: float = 0.1,
    ):
        """Initialize the DataModule

        args:
            N_samples: the number of points to sample
            domains: a list of domains to sample from, where a domain is a list of
                     tuples denoting the min/max range for each dimension
            split: the fraction of sampled data to reserve for validation
        """
        super().__init__()

        # Define the sample and batch sizes
        self.N_samples = N_samples
        self.split = split
        self.batch_size = 64

        # Define the sampling intervals
        # (we allow for multiple domains in case you need to sample extra around
        # the origin, for example)
        self.n_dims = Quad2D.N_DIMS
        if domains is None:
            self.domains = [
                [
                    (-4.0, 4.0),  # x
                    (-4.0, 4.0),  # z
                    (-np.pi, np.pi),  # theta
                    (-10.0, 10.0),  # vx
                    (-10.0, 10.0),  # vz
                    (-np.pi, np.pi),  # roll
                ],
                [
                    (-0.5, 0.5),
                    (-0.5, 0.5),
                    (-0.4 * np.pi, 0.4 * np.pi),
                    (-1.0, 1.0),
                    (-1.0, 1.0),
                    (-np.pi, np.pi),
                ],
            ]
        else:
            for domain in domains:
                assert len(domain) == self.n_dims
            self.domains = domains

        # Since we sample N_samples from each domain, the total number of samples
        # might be more than just N_samples
        self.N = len(self.domains) * N_samples

    def prepare_data(self):
        """Create the dataset by randomly sampling from the domains"""
        # Loop through each domain, sample from it, and store the samples in this list
        x_samples = []
        for domain in self.domains:
            # Sample all dimensions from [0, 1], then scale and shift as needed
            x_sample = torch.Tensor(self.N_samples, self.n_dims).uniform_(0.0, 1.0)
            for i in range(self.n_dims):
                min_val, max_val = domain[i]
                x_sample[:, i] = x_sample[:, i] * (max_val - min_val) + min_val

            # Save the sample from this domain
            x_samples.append(x_sample)

        # Concatenate all the samples into one big tensor
        x = torch.vstack(x_samples)

        # Create the safe/unsafe masks for the sampled points
        safe_mask = safe_mask_fn(x)
        unsafe_mask = unsafe_mask_fn(x)

        # Combine all of these into a single dataset and save it
        self.dataset = TensorDataset(x, safe_mask, unsafe_mask)

    def setup(self, stage=None):
        """Setup the data for training and validation"""
        # The data were generated randomly, so no need to do a random split
        split_pt = int(self.N * self.split)
        self.train_data = self.dataset[split_pt:]
        self.validation_data = self.dataset[:split_pt]

    def train_dataloader(self):
        """Make the DataLoader for training data"""
        return DataLoader(self.train_data, batch_size=self.batch_size)

    def val_dataloader(self):
        """Make the DataLoader for validation data"""
        return DataLoader(self.validation_data, batch_size=self.batch_size)