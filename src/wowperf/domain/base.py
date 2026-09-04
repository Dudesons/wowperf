# ABOUTME: The shared immutability base for every domain model.
# ABOUTME: One definition of frozen so the config can't drift between modules.

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)
