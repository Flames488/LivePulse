import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '1m',
};

const BASE_URL = __ENV.API_BASE_URL;
const TOKEN = __ENV.TEST_JWT;

export default function () {
  const payload = JSON.stringify({
    match_id: 123,
    round_id: 456,
    prediction: 'GOAL',
  });

  const headers = {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json',
  };

  const res = http.post(
    `${BASE_URL}/api/v1/predictions`,
    payload,
    { headers }
  );

  check(res, {
    'prediction accepted or locked': (r) =>
      r.status === 200 || r.status === 423,
  });

  sleep(1);
}
