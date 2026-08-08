const { handleLeadRequest } = require('../../server/lead-core');

exports.handler = async function handler(event){
  const result = await handleLeadRequest({ method:event.httpMethod, headers:event.headers, body:event.body });
  return { statusCode:result.status, headers:result.headers, body:result.body };
};
