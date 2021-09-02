from typing import Tuple, Optional

import cvxpy as cp
import torch
import numpy as np

from neural_clbf.systems import ObservableSystem, PlanarLidarSystem  # noqa
from neural_clbf.controllers.controller import Controller
from neural_clbf.experiments import ExperimentSuite


class ObsMPCController(Controller):
    """
    A comparison controller that implements MPC for perception-based control
    """

    def __init__(
        self,
        dynamics_model: ObservableSystem,
        controller_period: float,
        experiment_suite: ExperimentSuite,
        validation_dynamics_model: Optional[ObservableSystem] = None,
    ):
        """Initialize the controller.

        args:
            dynamics_model: the control-affine dynamics of the underlying system
            controller_period: the controller update period
            experiment_suite: defines the experiments to run during training
            validation_dynamics_model: optionally provide a dynamics model to use during
                                       validation
        """
        super(ObsMPCController, self).__init__(
            dynamics_model=dynamics_model,
            experiment_suite=experiment_suite,
            controller_period=controller_period,
        )

        # Define this again so that Mypy is happy
        self.dynamics_model = dynamics_model
        # And save the validation model
        self.training_dynamics_model = dynamics_model
        self.validation_dynamics_model = validation_dynamics_model

        # Save the experiments suits
        self.experiment_suite = experiment_suite

    def get_observations(self, x: torch.Tensor) -> torch.Tensor:
        """Wrapper around the dynamics model to get the observations"""
        assert isinstance(self.dynamics_model, ObservableSystem)
        return self.dynamics_model.get_observations(x)

    def approximate_lookahead(
        self, x: torch.Tensor, o: torch.Tensor, u: torch.Tensor, dt: float
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Wrapper around the dynamics model to do approximate lookeahead"""
        assert isinstance(self.dynamics_model, ObservableSystem)
        return self.dynamics_model.approximate_lookahead(x, o, u, dt)

    def u(self, x: torch.Tensor) -> torch.Tensor:
        """Returns the control input at a given state. Computes the observations and
        barrier function value at this state before computing the control.

        args:
            x: bs x self.dynamics_model.n_dims tensor of state
        """
        # Get the observations
        obs = self.get_observations(x)

        # Solve the MPC problem for each element of the batch
        batch_size = x.shape[0]
        u = torch.zeros(batch_size, self.dynamics_model.n_controls).type_as(x)
        for batch_idx in range(batch_size):
            batch_obs = obs[batch_idx, :, :]
            batch_x = x[batch_idx, :2].cpu().detach().numpy()

            # Compute an ellipsoid under-approximating the free space.
            # Parameterize the ellipsoid as the 1-sublevel set of x^T P x
            P = cp.Variable((2, 2), symmetric=True)

            # The operator >> denotes matrix inequality. We want P to be PSD
            constraints = [P >> 0]

            # For each detected point, we want x^T P x >= 1.1
            for point_idx in range(batch_obs.shape[-1]):
                o_i = batch_obs[:, point_idx].reshape(-1, 1).cpu().detach().numpy()
                constraints.append(cp.quad_form(o_i, P) >= 1.25)

            # Solve for the P with largest volume
            prob = cp.Problem(
                cp.Maximize(cp.log_det(P) - 100 * cp.trace(P)), constraints
            )
            prob.solve()
            # Skip if no solution
            if prob.status != "optimal":
                continue

            # Otherwise, continue on
            P_opt = P.value

            # Next, solve for the point inside that ellipsoid closest to the origin
            x_target = cp.Variable(2)

            # x_target and P are in the local frame, so we need a rotation to
            # compare with the global origin
            theta = x[batch_idx, 2].cpu().detach().numpy()
            rotation_mat = np.array(
                [
                    [np.cos(theta), -np.sin(theta)],
                    [np.sin(theta), np.cos(theta)],
                ]
            )

            objective = cp.sum_squares(batch_x + rotation_mat @ x_target)

            # We also want x_target to be within the ellipsoid
            constraints.append(cp.quad_form(x_target, P_opt) <= 0.75)

            # Solve for the target point
            prob = cp.Problem(cp.Minimize(objective), constraints)
            prob.solve()
            x_target_opt = x_target.value

            # Skip if no solution
            if prob.status != "optimal":
                continue

            # and convert to the global frame
            x_target_opt = rotation_mat @ x_target_opt

            # Now navigate towards that point by offsetting x from this target point
            # (shifting the origin) and applying the nominal controller
            x_shifted = torch.tensor(-x_target_opt).type_as(x)
            x_shifted = torch.cat((x_shifted, x[batch_idx, 2].unsqueeze(-1)))
            u[batch_idx, :] = self.dynamics_model.u_nominal(
                x_shifted.reshape(1, -1)
            ).squeeze()

            # # DEBUG
            # fig, ax = plt.subplots()
            # dynamics_model = cast("PlanarLidarSystem", self.dynamics_model)
            # dynamics_model.scene.plot(ax)
            # ax.set_aspect("equal")

            # ax.plot(x[batch_idx, 0], x[batch_idx, 1], "ro")
            # ax.plot(batch_x[0] + x_target_opt[0], batch_x[1] + x_target_opt[1], "bo")
            # ax.plot(x_shifted[0], x_shifted[1], "rx")
            # ax.plot(0 * x_shifted[0], 0 * x_shifted[1], "rx")

            # x_nexts, _ = self.approximate_lookahead(
            #     x[batch_idx, :].unsqueeze(0),
            #     batch_obs.unsqueeze(0),
            #     u[batch_idx, :].unsqueeze(0),
            #     self.controller_period,
            # )
            # ax.plot(x_nexts[0, 0], x_nexts[0, 1], "go")

            # lidar_pts = obs[batch_idx, :, :]
            # rotation_mat = torch.tensor(
            #     [
            #         [torch.cos(x[batch_idx, 2]), -torch.sin(x[batch_idx, 2])],
            #         [torch.sin(x[batch_idx, 2]), torch.cos(x[batch_idx, 2])],
            #     ]
            # )
            # lidar_pts = rotation_mat @ lidar_pts
            # lidar_pts[0, :] += x[batch_idx, 0]
            # lidar_pts[1, :] += x[batch_idx, 1]
            # ax.plot(lidar_pts[0, :], lidar_pts[1, :], "k-o")

            # x_plt = -np.linspace(-5.0, 5.0, 300)
            # y_plt = np.linspace(-5.0, 5.0, 300)

            # X_plt, Y_plt = np.meshgrid(x_plt, y_plt)

            # P_plot = rotation_mat.numpy() @ P_opt @ rotation_mat.numpy().T
            # ellipse_val = (
            #    P_plot[0, 0] * X_plt ** 2 + 2 * P_plot[1, 0] * X_plt * Y_plt
            #    + P_plot[1, 1] * Y_plt ** 2
            # )
            # Z = 1

            # plt.contour(X_plt + batch_x[0], Y_plt + batch_x[1], ellipse_val, [Z])

            # mng = plt.get_current_fig_manager()
            # mng.resize(*mng.window.maxsize())
            # plt.show()
            # # DEBUG

        # Scale the velocities a bit
        u[:, 0] *= 2.0
        u_upper, u_lower = self.dynamics_model.control_limits
        u = torch.clamp(u, u_lower, u_upper)

        return u
