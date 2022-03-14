import jax
import jax.numpy as jnp
import chex
from typing import Tuple
from functools import partial
from .termination import min_gen_criterion


class RestartWrapper(object):
    def __init__(self, base_strategy, stop_criteria=[]):
        """Base Class for a Restart Strategy."""
        self.base_strategy = base_strategy
        self.stop_criteria = stop_criteria

    @property
    def num_dims(self) -> int:
        """Get number of problem dimensions from base strategy."""
        return self.base_strategy.num_dims

    @property
    def popsize(self) -> int:
        """Get population size from base strategy."""
        return self.base_strategy.popsize

    @property
    def default_params(self) -> chex.ArrayTree:
        """Return default parameters of evolution strategy."""
        base_params = self.base_strategy.default_params
        params = {**base_params, **self.restart_params}
        return params

    @property
    def restart_params(self) -> chex.ArrayTree:
        """Return default parameters for strategy restarting."""
        re_params = {"min_num_gens": 50}
        return re_params

    @partial(jax.jit, static_argnums=(0,))
    def initialize(
        self, rng: chex.PRNGKey, params: chex.ArrayTree
    ) -> chex.ArrayTree:
        """`initialize` the evolution strategy."""
        state = self.base_strategy.initialize(rng, params)
        state["restart_counter"] = 0
        state["restarted"] = False
        return state

    @partial(jax.jit, static_argnums=(0,))
    def ask(
        self, rng: chex.PRNGKey, state: chex.ArrayTree, params: chex.ArrayTree
    ) -> Tuple[chex.Array, chex.ArrayTree]:
        """`ask` for new parameter candidates to evaluate next."""
        x, state = self.base_strategy.ask(rng, state, params)
        return x, state

    @partial(jax.jit, static_argnums=(0,))
    def tell(
        self,
        rng: chex.PRNGKey,
        x: chex.Array,
        fitness: chex.Array,
        state: chex.ArrayTree,
        params: chex.ArrayTree,
    ) -> chex.ArrayTree:
        """`tell` performance data for strategy state update."""
        state = self.base_strategy.tell(x, fitness, state, params)
        restart_bool = self.stop(fitness, state, params)
        restart_state = self.restart(rng, fitness, state, params)
        new_state = jax.tree_multimap(
            lambda x, y: jax.lax.select(restart_bool, x, y),
            restart_state,
            state,
        )
        new_state["restarted"] = restart_bool
        return new_state

    @partial(jax.jit, static_argnums=(0,))
    def stop(
        self, fitness: chex.Array, state: chex.ArrayTree, params: chex.ArrayTree
    ) -> bool:
        """Check all stopping criteria & return stopping bool indicator."""
        restart_bool = 0
        # Loop over stop criteria functions - stop if one is fullfilled
        for crit in self.stop_criteria:
            restart_bool += crit(fitness, state, params)
        # Check if minimal number of generations has passed!
        return jnp.logical_and(
            restart_bool > 0, min_gen_criterion(fitness, state, params)
        )

    def restart(
        self,
        rng: chex.PRNGKey,
        fitness: chex.Array,
        state: chex.ArrayTree,
        params: chex.ArrayTree,
    ) -> chex.ArrayTree:
        """Restart state for next generations."""
        new_state = self.restart_strategy(rng, fitness, state, params)
        # Copy over important parts of state from previous strategy
        new_state["best_fitness"] = state["best_fitness"]
        new_state["best_member"] = state["best_member"]
        new_state["restart_counter"] = state["restart_counter"] + 1
        new_state["restarted"] = True
        return new_state

    def restart_strategy(
        self,
        rng: chex.PRNGKey,
        fitness: chex.Array,
        state: chex.ArrayTree,
        params: chex.ArrayTree,
    ) -> chex.ArrayTree:
        """Restart strategy specific new state construction."""
        raise NotImplementedError