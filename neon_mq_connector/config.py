# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import json
from typing import Optional
from ovos_utils.log import LOG
from ovos_config.config import Configuration as _Config
from ovos_config.locations import get_xdg_config_save_path


def load_neon_mq_config():
    """
    Locates and loads global MQ configuration. Priority is as follows:
    NEON_MQ_CONFIG_PATH environment variable
    {NEON_CONFIG_PATH}/mq_config.json
    ~/.local/share/neon/credentials.json
    """
    valid_config_paths = (
        os.path.expanduser(os.environ.get('NEON_MQ_CONFIG_PATH', "")),
        os.path.join(get_xdg_config_save_path("neon"), "mq_config.json"),
        os.path.expanduser("~/.local/share/neon/credentials.json")
    )
    config = None
    for conf in valid_config_paths:
        if conf and os.path.isfile(conf):
            LOG.warning(f"Legacy configuration found at {conf}")
            with open(conf) as f:
                config = json.load(f)
            break
    if not config:
        config = _Config()
    return config.get("MQ", config)


class Configuration:
    def __init__(self, file_path: Optional[str] = None):
        LOG.warning("This class is deprecated. "
                    "Parse configuration files to dict or use `ovos_config`")
        self._config_data = dict()
        if file_path:
            self.from_file(file_path)

    def from_file(self, file_path: str):
        with open(os.path.expanduser(file_path)) as input_file:
            self._config_data = json.load(input_file)
        return self

    def from_dict(self, config_data: dict):
        self._config_data = config_data
        return self

    @property
    def config_data(self) -> dict:
        return self._config_data

    @config_data.setter
    def config_data(self, value):
        if not isinstance(value, dict):
            raise TypeError(f'Type: {type(value)} not supported')
        self._config_data = value
