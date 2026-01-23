import { useQuery } from '@tanstack/react-query';
import { getPositions, getPositionHistory } from '../../../services/api';

export function usePositionsQuery() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: getPositions,
    refetchInterval: 10000,
  });
}

export function usePositionHistoryQuery(limit = 50) {
  return useQuery({
    queryKey: ['positionHistory', limit],
    queryFn: () => getPositionHistory(limit),
    refetchInterval: 30000,
  });
}
