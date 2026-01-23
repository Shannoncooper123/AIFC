import { Wallet, TrendingUp, TrendingDown, Shield } from 'lucide-react';
import type { AccountSummary } from '../../../types';
import { Card } from '../../../components/ui';

interface AccountCardProps {
  account: AccountSummary;
}

export function AccountCard({ account }: AccountCardProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number | undefined) => {
    if (value === undefined) return '-';
    return `${(value * 100).toFixed(2)}%`;
  };

  const pnlIsPositive = account.unrealized_pnl >= 0;

  return (
    <Card title="Account">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Wallet className="h-4 w-4" />
            <span>Total Balance</span>
          </div>
          <p className="text-xl font-semibold text-gray-100">
            {formatCurrency(account.total_balance)}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Wallet className="h-4 w-4" />
            <span>Available</span>
          </div>
          <p className="text-xl font-semibold text-gray-100">
            {formatCurrency(account.available_balance)}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            {pnlIsPositive ? (
              <TrendingUp className="h-4 w-4 text-green-400" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-400" />
            )}
            <span>Unrealized PnL</span>
          </div>
          <p
            className={`text-xl font-semibold ${
              pnlIsPositive ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {pnlIsPositive ? '+' : ''}
            {formatCurrency(account.unrealized_pnl)}
          </p>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Shield className="h-4 w-4" />
            <span>Margin Used</span>
          </div>
          <p className="text-xl font-semibold text-gray-100">
            {formatCurrency(account.margin_used)}
          </p>
          {account.margin_ratio !== undefined && (
            <p className="text-xs text-gray-500">
              Ratio: {formatPercent(account.margin_ratio)}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
