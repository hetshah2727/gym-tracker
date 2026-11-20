from decimal import ROUND_HALF_UP, Decimal

from app.core.config import settings

CENT = Decimal("0.01")


def split_commission(commission: float, has_trainer: bool) -> dict[str, float]:
    """Split one commission between platform, gym and trainer.

    Shares come from settings (default 20 / 30 / 50). If no trainer referred the
    sale, the trainer's share goes to the gym. Rounding remainders go to the
    platform so the three parts always add up to the commission exactly.
    """
    total = Decimal(str(commission)).quantize(CENT, ROUND_HALF_UP)
    gym_pct = Decimal(str(settings.GYM_SHARE_PCT))
    trainer_pct = Decimal(str(settings.TRAINER_SHARE_PCT))
    if not has_trainer:
        gym_pct, trainer_pct = gym_pct + trainer_pct, Decimal(0)
    gym = (total * gym_pct / 100).quantize(CENT, ROUND_HALF_UP)
    trainer = (total * trainer_pct / 100).quantize(CENT, ROUND_HALF_UP)
    platform = total - gym - trainer
    return {"commission_amount": float(total), "platform_share": float(platform),
            "gym_share": float(gym), "trainer_share": float(trainer)}
