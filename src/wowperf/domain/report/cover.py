# ABOUTME: Re-exports of the aura window arithmetic, which now lives in domain/auras.py
# ABOUTME: beside the models it reads. Kept so this module's own importers need not change.

from wowperf.domain.auras import band_holding, clipped_bands, resolve_aura

__all__ = ["band_holding", "clipped_bands", "resolve_aura"]
