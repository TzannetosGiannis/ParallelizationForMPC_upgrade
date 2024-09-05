import os
from enum import Enum
from typing import Any

from . import motion, mp_spdz
from ..loop_linear_code import Function
from ..type_analysis import TypeEnv
from ..util import assert_never
from ..protocol_mixing import Config


class Backend(Enum):
    MOTION = "MOTION"
    MP_SPDZ = "MP-SPDZ"

    def __str__(self) -> str:
        return self.value

    def render_function(
        self, func: Function, type_env: TypeEnv, ran_vectorization: bool
    ) -> str:
        if self is Backend.MOTION:
            return motion.render_function(func, type_env, ran_vectorization)
        elif self is Backend.MP_SPDZ:
            return mp_spdz.render_function(func, type_env, ran_vectorization)
        else:
            assert_never(self)

    def render_mixed_function(
        self, func: Function, type_env: TypeEnv, ran_vectorization: bool,mixed_config:Config
    ) -> str:
        if self is Backend.MOTION:
            return motion.render_mixed_function(func, type_env, ran_vectorization,mixed_config)
        elif self is Backend.MP_SPDZ:
            # assert_never(self)
            # [TODO] change this to the mixed version when available
            return mp_spdz.render_function(func, type_env, ran_vectorization)
        else:
            assert_never(self)

    def render_application(
        self,
        func: Function,
        type_env: TypeEnv,
        params: dict[str, Any],
        ran_vectorization: bool,
    ) -> None:
        if self is Backend.MOTION:
            return motion.render_application(func, type_env, params, ran_vectorization)
        elif self is Backend.MP_SPDZ:
            return mp_spdz.render_application(func, type_env, params, ran_vectorization)
        else:
            assert_never(self)

    def valid_protocols(self) -> list[str]:
        if self is Backend.MOTION:
            return motion.VALID_PROTOCOLS
        elif self is Backend.MP_SPDZ:
            return mp_spdz.VALID_PROTOCOLS
        else:
            assert_never(self)

    def submodule_path(self) -> str:
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        return os.path.join(project_root, "backend_submodules", self.value)
