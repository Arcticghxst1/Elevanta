import express from "express";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";

const router = express.Router();

router.post("/register", async (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) {
        return res.status(400).json({ message: "username and password required" });
    }

    try {
        const existingUser = await mysql.user.findUnique({
            where: { username }
        });

        if (existingUser) {
            return res.status(400).json({ message: "User already exists" });
        }

        const hashedPassword = bcrypt.hashSync(password, 8);
        const user = await mysql.user.create({
            data: {
                username,
                password: hashedPassword
            }
        });

        const token = jwt.sign({ id: user.id }, process.env.JWT_SECRET, { expiresIn: "14h" });
        return res.status(201).json({ id: user.id, token, message: "User registered successfully" });
    } catch (err) {
        console.error("Register error:", err.message);
        return res.status(500).json({ message: "Internal server error" });
    }
});

router.post("/login", async (req, res) => {
    const { username, password } = req.body;

    if (!username || !password) {
        return res.status(400).json({ message: "username and password required" });
    }

    try {
        const user = await mysql.user.findUnique({
            where: { username }
        });

        if (!user) {
            return res.status(400).json({ message: "Invalid username or password" });
        }

        const passwordOk = bcrypt.compareSync(password, user.password);
        if (!passwordOk) {
            return res.status(400).json({ message: "Invalid username or password" });
        }

        const token = jwt.sign({ id: user.id }, process.env.JWT_SECRET, { expiresIn: "14h" });
        return res.json({ token });
    } catch (err) {
        console.error("Login error:", err.message);
        return res.status(500).json({ message: "Internal server error" });
    }
});

export default router;
