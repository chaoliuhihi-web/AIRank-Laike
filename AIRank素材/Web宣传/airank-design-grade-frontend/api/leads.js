const { handleLeadRequest } = require('../server/lead-core');

module.exports = async function handler(req, res){
  const result = await handleLeadRequest({ method:req.method, headers:req.headers, body:req.body });
  res.statusCode = result.status;
  for (const [key, value] of Object.entries(result.headers)) res.setHeader(key, value);
  res.end(result.body);
};
