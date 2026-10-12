from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import math
from typing import Any, Dict, Optional
from app.core.config import settings


def amount(value: Decimal) -> float:
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class OwnerAddOnAdvisor:
    """Separate total portfolio value, available add-on cash and technical entry.

    Capacity is conditional on a valid setup. Missing cash preserves the legacy
    portfolio-limit calculation, but is explicitly disclosed as unconfirmed cash.
    """

    @classmethod
    def evaluate(cls, current_price: float, capital: float, shares_owned: Optional[int],
                 trade_plan: Optional[Dict[str, Any]], sessions_behind: Optional[int],
                 buy_price: Optional[float] = None, add_on_cash: Optional[float] = None) -> Dict[str, Any]:
        inputs = [current_price, capital] + ([buy_price] if buy_price is not None else []) + ([add_on_cash] if add_on_cash is not None else [])
        if (any(not math.isfinite(value) for value in inputs) or current_price <= 0 or capital <= 0 or
                (buy_price is not None and buy_price <= 0) or (add_on_cash is not None and not 0 <= add_on_cash <= capital)):
            return cls._result('INVALID_INPUT', 'راجع المدخلات', 'أدخل إجمالي محفظة وسعرًا صحيحين، ومبلغ تعزيز بين صفر وإجمالي المحفظة.')
        if (shares_owned is None or isinstance(shares_owned, bool) or not math.isfinite(shares_owned)
                or shares_owned <= 0 or int(shares_owned) != shares_owned):
            return cls._result('MISSING_POSITION_DATA', 'أدخل بيانات المركز', 'يلزم عدد الأسهم المملوكة الصحيح لحساب مساحة التعزيز؛ لن نفترض أن مركزك صفر.')
        if sessions_behind != 0:
            return cls._result('DATA_NOT_CURRENT', 'لا تعزز الآن', 'بيانات آخر جلسة غير محدثة، لذلك لا يمكن تقييم التعزيز بأمان.')
        if not trade_plan or trade_plan.get('plan_status') == 'NO_VALID_SETUP':
            return cls._result('NO_VALID_SETUP', 'لا تعزز الآن', 'لا توجد خطة دخول حالية صالحة للتعزيز. انتظر تكوين إعداد فني جديد من بيانات جلسة مكتملة.')
        try:
            zone_min, zone_max, stop = [Decimal(str(trade_plan[key])) for key in ('entry_zone_min', 'entry_zone_max', 'stop_loss')]
            if not all(value.is_finite() for value in (zone_min, zone_max, stop)) or not 0 < stop < zone_min <= zone_max:
                raise ValueError()
        except (KeyError, ValueError, TypeError, ArithmeticError):
            return cls._result('NO_VALID_SETUP', 'لا تعزز الآن', 'الخطة الحالية لا تحتوي على منطقة دخول ووقف خسارة صالحين للتعزيز.')

        if Decimal(str(current_price)) <= stop:
            return cls._result('DO_NOT_ADD', 'لا تعزز', f'السعر الحالي {current_price:.2f} ج.م كسر الوقف {stop:.2f} ج.م. يلزم إعداد فني صالح قبل حساب تعزيز جديد.', float(zone_min), float(zone_max))
        if trade_plan.get('plan_status') in ('INVALIDATED', 'TARGETS_COMPLETED'):
            return cls._result('DO_NOT_ADD', 'لا تعزز', 'الخطة الحالية ملغاة أو حققت أهدافها؛ انتظر خطة جديدة قبل حساب كمية التعزيز.', float(zone_min), float(zone_max))

        price, portfolio = Decimal(str(current_price)), Decimal(str(capital))
        cash = Decimal(str(add_on_cash)) if add_on_cash is not None else None
        owned = int(shares_owned)
        # At an eligible live price calculate the actual prospective purchase;
        # while waiting use the zone's upper boundary for a conditional scenario.
        entry = price if zone_min <= price <= zone_max else zone_max
        valuation = max(price, entry)
        allocation_limit = portfolio * Decimal(str(settings.MAX_ALLOCATION_PCT))
        risk_limit = portfolio * Decimal(str(settings.MAX_RISK_PER_TRADE_PCT))
        position_value = price * owned
        reserved_position_value = valuation * owned
        existing_risk = max(valuation - stop, Decimal(0)) * owned
        remaining_allocation = max(allocation_limit - reserved_position_value, Decimal(0))
        remaining_risk = max(risk_limit - existing_risk, Decimal(0))
        per_share_risk = entry - stop
        def whole(value):
            return int(value.to_integral_value(rounding=ROUND_FLOOR))
        by_allocation = whole(remaining_allocation / entry)
        by_risk = whole(remaining_risk / per_share_risk)
        by_cash = whole(cash / entry) if cash is not None else None
        constraints = {'ALLOCATION': by_allocation, 'RISK': by_risk}
        if by_cash is not None:
            constraints['CASH'] = by_cash
        count = min(constraints.values())
        added_value = count * entry
        total_shares = owned + count
        average = (Decimal(str(buy_price)) * owned + added_value) / total_shares if buy_price is not None else None
        sizing = {
            'current_position_value_egp': amount(position_value),
            'max_total_allocation_egp': amount(allocation_limit),
            'remaining_allocation_egp': amount(remaining_allocation),
            'existing_risk_to_stop_egp': amount(existing_risk),
            'remaining_risk_budget_egp': amount(remaining_risk),
            'suggested_add_on_shares': count, 'estimated_add_on_value_egp': amount(added_value),
            'portfolio_capital_egp': amount(portfolio), 'available_add_on_cash_egp': amount(cash) if cash is not None else None,
            'cash_constraint_applied': cash is not None, 'sizing_price': float(entry),
            'sizing_price_basis': 'CURRENT_PRICE_IN_ZONE' if entry == price else 'ENTRY_ZONE_UPPER_BOUND',
            'valuation_price': float(valuation), 'reserved_position_value_egp': amount(reserved_position_value),
            'max_allocation_pct': 100 * settings.MAX_ALLOCATION_PCT,
            'max_risk_pct': 100 * settings.MAX_RISK_PER_TRADE_PCT, 'max_risk_allowed_egp': amount(risk_limit),
            'risk_per_added_share_egp': amount(per_share_risk),
            'shares_by_allocation': by_allocation, 'shares_by_risk': by_risk, 'shares_by_cash': by_cash,
            'limiting_factors': [key for key, value in constraints.items() if value == count],
            'shares_after_add_on': total_shares, 'average_buy_price_after_add_on': float(average.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)) if average is not None else None,
            'remaining_cash_after_add_on_egp': amount(cash - added_value) if cash is not None else None,
            'position_value_after_add_on_egp': amount(reserved_position_value + added_value),
            'risk_to_stop_after_add_on_egp': amount(existing_risk + count * per_share_risk),
            'executable_add_on_shares': 0,
        }
        if count == 0:
            reasons = []
            if by_allocation == 0:
                reasons.append(f'قيمة المركز المحجوزة للحساب {reserved_position_value:.2f} ج.م مقابل حد تخصيص {allocation_limit:.2f} ج.م ({100 * settings.MAX_ALLOCATION_PCT:g}% من المحفظة)')
            if by_risk == 0:
                reasons.append(f'مخاطرة المركز حتى الوقف {existing_risk:.2f} ج.م مقابل حد {risk_limit:.2f} ج.م ({100 * settings.MAX_RISK_PER_TRADE_PCT:g}%)')
            if by_cash == 0:
                reasons.append(f'مبلغ التعزيز المتاح {cash:.2f} ج.م لا يكفي لسهم بسعر الحساب {entry:.2f} ج.م')
            return cls._result('NO_ADD_CAPACITY', 'لا تعزز الآن', '؛ '.join(reasons) + '. المساحة المتبقية لا تسمح بسهم إضافي ضمن الحدود.', float(zone_min), float(zone_max), sizing)
        if zone_min <= price <= zone_max:
            sizing['executable_add_on_shares'] = count if cash is not None else 0
            if cash is None:
                return cls._result('CASH_NOT_SPECIFIED', 'حدد مبلغ التعزيز', 'السعر داخل النطاق وهناك سعة ضمن التخصيص والمخاطرة. أدخل الكاش المتاح لتحديد عدد يمكن تمويله فعليًا.', float(zone_min), float(zone_max), sizing)
            return cls._result('ADD_NOW', 'تعزيز ضمن الحدود', f'السعر داخل منطقة التعزيز. الحساب يسمح حتى {count} سهم بسعر {entry:.2f} ج.م ضمن الكاش والتخصيص والمخاطرة.', float(zone_min), float(zone_max), sizing)
        if price > zone_max:
            return cls._result('WAIT_TO_ADD', 'انتظر للتعزيز', f'السعر أعلى منطقة {zone_min:.2f} – {zone_max:.2f} ج.م. الكمية أدناه سيناريو مشروط بالعودة للنطاق وليست تنفيذًا الآن.', float(zone_min), float(zone_max), sizing)
        return cls._result('WAIT_CONFIRMATION', 'انتظر تأكيدًا قبل التعزيز', f'السعر أسفل منطقة {zone_min:.2f} – {zone_max:.2f} ج.م وأعلى الوقف. انتظر ارتدادًا داخل النطاق.', float(zone_min), float(zone_max), sizing)

    @staticmethod
    def _result(code, label_ar, reason_ar, zone_min=None, zone_max=None, sizing=None):
        return {'decision': code, 'decision_ar': label_ar, 'reason_ar': reason_ar,
                'entry_zone_min': zone_min, 'entry_zone_max': zone_max, 'sizing': sizing}
