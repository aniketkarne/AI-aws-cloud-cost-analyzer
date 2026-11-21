import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { toChartPoints } from '../lib/chartData';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

interface CostChartProps {
  data: Array<Record<string, any>>;
  labelKey: string;
  valueKey: string;
  title?: string;
}

const CostChart: React.FC<CostChartProps> = ({
  data,
  labelKey,
  valueKey,
  title = 'Cost Breakdown'
}) => {
  // Result rows carry the raw column names of the LLM-generated SQL, so the
  // expected keys are only a preference; non-numeric rows are dropped.
  const points = toChartPoints(data, labelKey, valueKey);

  if (points.length === 0) {
    return (
      <p className="text-gray-500">
        No numeric column to plot in these results.
      </p>
    );
  }

  const chartData = {
    labels: points.map((p) => p.label),
    datasets: [
      {
        label: valueKey,
        data: points.map((p) => p.value),
        backgroundColor: 'rgba(25, 118, 210, 0.7)',
      }
    ]
  };

  const options = {
    responsive: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: title }
    }
  };

  return <Bar data={chartData} options={options} />;
};

export default CostChart;
