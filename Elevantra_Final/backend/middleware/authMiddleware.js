import jwt from 'jsonwebtoken'

function authMiddleware (req, res, next) {
    const authHeader = req.headers.authorization

    if (!authHeader) {
        console.warn('Auth middleware: No Autthorization header provided')
        return res.status(401).json({ message: 'No token provided'})
    }

    const token = authHeader.startsWith('Bearer') ? authHeader.slice(7) : authHeader

    if (!process.env.JWT_SECRET) {
        console.error('Auth middleware: JWT_SECRET is not configured')
        return res.status(500).json({ message: 'Authentication configuration error' })
    }
    
    jwt.verify(token, process.env.JWT_SECRET, (err, decoded) => {
        if (err) {
            console.error('Auth middleware: token verification failed', err.name, err.message)
            return res.status(401).json({ message: 'Invalid Token payload' })
        }

        req.userID = decoded.id 
        next()

    })
}

export default authMiddleware 