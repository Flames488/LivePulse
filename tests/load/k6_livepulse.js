import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 },   // ramp up
    { duration: '1m', target: 100 },   // sustained load
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';

export default function () {
  const res = http.get(`${BASE_URL}/health`);

  check(res, {
    'health endpoint OK': (r) => r.status === 200,
  });

  sleep(1);
}
