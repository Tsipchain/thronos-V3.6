const PROJECT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

module.exports = ({ config }) => {
  const projectId = String(process.env.EAS_PROJECT_ID || '').trim();
  if (projectId && !PROJECT_ID_RE.test(projectId)) {
    throw new Error('EAS_PROJECT_ID must be the genuine Expo project UUID');
  }

  const extra = { ...(config.extra || {}) };
  if (projectId) extra.eas = { projectId };
  else delete extra.eas;

  return {
    ...config,
    extra,
  };
};
